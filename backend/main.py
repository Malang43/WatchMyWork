import io
import json
import logging
import os
import re
from urllib.parse import urlsplit
from fastapi.staticfiles import StaticFiles
from . import config
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from . import storage as store, executor
from .inference import infer, InferenceError, InferenceUnavailable, compile_demonstration, MODEL
from .schema import Workflow, TeachRequest, EventBatch, InferRequest, RunRequest, Resolution, TARGETS, WEATHER_CLICK, WEATHER_RESULT, columns_of, input_bindings, row_key, valid_coordinates, valid_temperature, demonstrated_plan, developer
from .sheets import read_sheet, export_sheet

DEMO_LOCK = threading.RLock()
INFER_BUSY = set()
INFER_PROGRESS = {}
logger = logging.getLogger('uvicorn.error')

@asynccontextmanager
async def lifespan(app):
    store.init()
    yield

app = FastAPI(title='WatchMyWork Local API', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[config.PUBLIC_ORIGIN] if config.PRODUCTION and config.PUBLIC_ORIGIN else ['http://127.0.0.1:5174'] if not config.PRODUCTION else [], allow_origin_regex=r'chrome-extension://[a-p]{32}', allow_methods=['GET', 'POST', 'PUT'], allow_headers=['Content-Type', 'X-WatchMyWork'])

@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.url.hostname
    allowed_hosts = {urlsplit(config.PUBLIC_ORIGIN).hostname} if config.PRODUCTION else {'127.0.0.1', 'localhost', 'testserver'}
    # Railway probes use their own Host; only the read-only health endpoint is exempt.
    if host not in allowed_hosts and not (config.PRODUCTION and request.url.path == '/health' and request.method in ('GET', 'HEAD')):
        return JSONResponse({'detail': 'Unrecognized application host'}, status_code=403)
    origin = request.headers.get('origin')
    allowed_origins = {config.PUBLIC_ORIGIN} if config.PRODUCTION else {'http://127.0.0.1:5174'}
    if origin and origin not in allowed_origins and not re.fullmatch(r'chrome-extension://[a-p]{32}', origin):
        return JSONResponse({'detail': 'Unrecognized application origin'}, status_code=403)
    if request.method in ('POST', 'PUT', 'DELETE') and request.headers.get('X-WatchMyWork') != 'local-demo':
        return JSONResponse({'detail': 'Missing local application header'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

def require(kind, item_id):
    item = store.get(kind, item_id)
    if not item:
        raise HTTPException(404, f'{kind.title()} not found')
    return item

def validate_columns(dataset, input_column, destination_column):
    if any(c not in dataset['columns'] for c in columns_of(input_column)) or destination_column not in dataset['columns'] or destination_column in columns_of(input_column):
        raise HTTPException(422, 'Choose different input and output columns present in this spreadsheet')

def validate_test_columns(dataset, mapping):
    if developer(mapping) and any(c not in dataset['columns'] for c in [mapping.expected_column, mapping.status_column]):
        raise HTTPException(422, 'Expected and status columns must exist in the spreadsheet')

def dataset_metadata(item):
    return {k: v for k, v in item.items() if k != 'rows'} | {'preview': item['rows'][:5], 'record_count': len(item['rows'])}

def usable_demos(request):
    dataset = require('dataset', request.dataset_id)
    validate_test_columns(dataset, request)
    validate_columns(dataset, request.input_columns, request.destination_column)
    demos = [d for d in store.listing('demo') if d['dataset_id'] == request.dataset_id and d['state'] == 'complete' and columns_of(d) == request.input_columns and d['destination_column'] == request.destination_column]
    if not demos:
        raise HTTPException(422, 'Record and stop at least one complete demonstration first')
    return [d for d in demos if d.get('mode', 'lookup') == request.mode and d.get('expected_column') == request.expected_column and d.get('status_column') == request.status_column] or _no_demos()

def _no_demos():
    raise HTTPException(422, 'Record a demonstration with this test mapping first')

def create_workflow(plan, request, demos, source, metric_id=None):
    workflow = store.put('workflow', {'id': store.uid(), 'plan': plan.model_dump(), 'created_at': store.now(), 'confirmed': False, 'saved': False, 'source': source, 'dataset_id': request.dataset_id, 'demo_ids': [d['id'] for d in demos], 'human_corrections': 0})
    if metric_id:
        with store.connect() as db:
            db.execute('UPDATE inference SET workflow_id=? WHERE id=? OR (workflow_id IS NULL AND dataset_id=?)', (workflow['id'], metric_id, request.dataset_id))
    return workflow

@app.get('/health')
def health():
    return {'ok': True, 'model': MODEL, 'api_key_configured': bool(os.getenv('OPENROUTER_API_KEY')), 'mock_url': config.WEATHER_URL}

@app.get('/sample')
def sample():
    return FileResponse(Path(__file__).resolve().parents[1] / 'sample-data' / 'tracking-demo.xlsx', filename='tracking-demo.xlsx')

@app.post('/datasets')
async def upload(file: UploadFile = File(...)):
    content = await file.read(10 * 1024 * 1024 + 1)
    try:
        columns, rows = read_sheet(content, file.filename or '')
    except Exception:
        raise HTTPException(422, 'Invalid spreadsheet. Use a UTF-8 CSV or .xlsx with unique headers, 1–10,000 rows, at most 100 columns, and under 10 MB.') from None
    item = store.put('dataset', {'id': store.uid(), 'filename': Path(file.filename.replace('\\', '/')).name[:200], 'columns': columns, 'rows': rows, 'created_at': store.now()})
    return dataset_metadata(item)

@app.get('/datasets/{item_id}')
def dataset(item_id: str):
    return dataset_metadata(require('dataset', item_id))

@app.get('/datasets/{item_id}/rows/{index}')
def dataset_row(item_id: str, index: int):
    item = require('dataset', item_id)
    if not 0 <= index < len(item['rows']):
        raise HTTPException(404, 'Row not found')
    return item['rows'][index]

@app.post('/demos')
def begin_demo(request: TeachRequest):
    dataset = require('dataset', request.dataset_id)
    validate_test_columns(dataset, request)
    validate_columns(dataset, request.input_columns, request.destination_column)
    if request.row_index >= len(dataset['rows']) or any(not dataset['rows'][request.row_index][c].strip() for c in request.input_columns):
        raise HTTPException(422, 'Choose a populated input row for your demonstration')
    if not developer(request) and len(request.input_columns) == 2 and not valid_coordinates([dataset['rows'][request.row_index][c] for c in request.input_columns]):
        raise HTTPException(422, 'Choose a row with valid latitude and longitude values')
    with DEMO_LOCK:
        if any(d['state'] == 'recording' for d in store.listing('demo')):
            raise HTTPException(409, 'Stop the current recording before starting another')
        return store.put('demo', {'id': store.uid(), **request.model_dump(), 'state': 'recording', 'created_at': store.now(), 'events': [], 'result': ''})

@app.get('/teach/current')
def current_demo():
    active = next((d for d in store.listing('demo') if d['state'] == 'recording'), None)
    if not active:
        return None
    dataset = require('dataset', active['dataset_id'])
    return {'id': active['id'], 'input_columns': columns_of(active), 'input_column': columns_of(active)[0], 'destination_column': active['destination_column'], 'input_values': {c: dataset['rows'][active['row_index']][c] for c in columns_of(active)}, 'mode': active.get('mode', 'lookup'), 'bindings': input_bindings(active)}

@app.get('/demos')
def demos(dataset_id: str):
    return [d for d in store.listing('demo') if d['dataset_id'] == dataset_id]

def demonstrated_result(demo):
    columns = columns_of(demo)
    bindings = input_bindings(demo)
    dev = developer(demo)
    weather = len(columns) == 2 and not dev
    expected = require('dataset', demo['dataset_id'])['rows'][demo['row_index']]
    filled = {}
    clicked = waited = False
    result = ''
    for event in demo['events']:
        action = event['action']
        if action == 'fill':
            filled[event['target']] = event['value']
            clicked = waited = False
            result = ''
        elif action == 'click':
            actual = {column: filled.get(target, '') for target, column in bindings.items()}
            clicked = all(target in filled for target in bindings) and (all(actual[c] == expected[c] for c in columns) if dev else row_key(actual, columns) == row_key(expected, columns))
            if weather:
                clicked = clicked and valid_coordinates([actual[c] for c in columns])
            waited = False
            result = ''
        elif action == 'wait' and clicked:
            waited = True
        elif action == 'extract' and clicked and (waited or not weather):
            if (bool(event['text'].strip()) if dev else valid_temperature(event['text']) if weather else event['text'] in executor.STATUSES):
                result = event['text']
    return result

@app.post('/demos/{item_id}/events')
def record_events(item_id: str, batch: EventBatch):
    with DEMO_LOCK:
        demo = require('demo', item_id)
        logger.info('recording received demonstration_id=%s event_count=%d', demo['id'], len(batch.events))
        if demo['state'] != 'recording':
            if demo['state'] == 'complete':
                return {'recorded': len(demo['events']), 'state': 'complete'}
            raise HTTPException(409, 'This demonstration is no longer recording')
        if len(demo['events']) + len(batch.events) > 300:
            raise HTTPException(422, 'Demonstration is too long; stop and record a shorter example')
        bindings = input_bindings(demo)
        dev = developer(demo)
        weather = len(columns_of(demo)) == 2
        click_target = '#login-button' if dev else WEATHER_CLICK
        result_target = '#login-result' if dev else WEATHER_RESULT
        for event in batch.events:
            targets = list(bindings) if event.action in ('fill', 'focus') else [click_target if weather else TARGETS['click']] if event.action == 'click' else [result_target if weather else TARGETS['extract']] if event.action in ('wait', 'extract') else [config.DEVELOPER_URL if dev else config.WEATHER_URL]
            if event.url != (config.DEVELOPER_URL if dev else config.WEATHER_URL) or event.target not in targets or (event.action == 'wait' and not weather):
                raise HTTPException(422, 'Record only supported elements on the local mock site')
            data = event.model_dump()
            data['label'] = bindings.get(event.target) or ('Login' if dev else 'Check Weather' if weather else 'Check Status') if event.action == 'click' else bindings.get(event.target) or ('Login result' if dev else 'Temperature result' if weather else 'Result')
            if event.action == 'navigate':
                data['label'] = 'Local demo site'
            data['role'] = {'fill': 'textbox', 'focus': 'textbox', 'click': 'button', 'wait': 'status', 'extract': 'status', 'navigate': 'document'}[event.action]
            demo['events'].append(data)
        if weather:
            result = demonstrated_result(demo)
            if result:
                demo.update(state='complete', result=result)
        store.put('demo', demo)
        logger.info('demonstration saved demonstration_id=%s state=%s', demo['id'], demo['state'])
        return {'recorded': len(demo['events']), 'state': demo['state']}

@app.post('/demos/{item_id}/stop')
def stop_demo(item_id: str):
    with DEMO_LOCK:
        demo = require('demo', item_id)
        if demo['state'] != 'recording':
            return demo
        result = demonstrated_result(demo)
        demo.update(state='complete' if result else 'incomplete', result=result)
        store.put('demo', demo)
        logger.info('demonstration saved demonstration_id=%s state=%s', demo['id'], demo['state'])
        return demo

@app.get('/inference/{dataset_id}/status')
def inference_status(dataset_id: str):
    require('dataset', dataset_id)
    return INFER_PROGRESS.get(dataset_id, {'attempt': 0, 'state': 'idle'})


@app.post('/workflows/infer')
async def infer_workflow(request: InferRequest):
    demos = usable_demos(request)
    if request.dataset_id in INFER_BUSY:
        raise HTTPException(409, 'Analysis is already running for this spreadsheet')
    INFER_BUSY.add(request.dataset_id)
    logger.info('inference request started demonstration_ids=%s', ','.join(d['id'] for d in demos))
    try:
        def progress(attempt):
            INFER_PROGRESS[request.dataset_id] = {'attempt': attempt, 'state': 'analyzing'}
        source = 'nemotron'
        try:
            plan, metric_id = await infer(demos, request, request.destination_column, request.dataset_id, progress=progress)
        except InferenceUnavailable as exc:
            print('Using semantic workflow fallback', flush=True)
            plan = compile_demonstration(demos, request, request.destination_column)
            metric_id, source = exc.metric_id, 'semantic_fallback'
        return create_workflow(plan, request, demos, source, metric_id)
    except InferenceError as exc:
        raise HTTPException(503, str(exc)) from None
    finally:
        INFER_BUSY.discard(request.dataset_id)
        INFER_PROGRESS.pop(request.dataset_id, None)

@app.post('/workflows/manual')
def manual_workflow(request: InferRequest):
    demos = usable_demos(request)
    return create_workflow(demonstrated_plan(request, request.destination_column), request, demos, 'manual')

@app.get('/workflows')
def workflows():
    runs = [executor.summary(r) for r in store.listing('run')]
    items = []
    for workflow in store.listing('workflow'):
        history = [r for r in runs if r['workflow_id'] == workflow['id']]
        last = history[0] if history else None
        items.append({**workflow, 'run_count': len(history), 'last_success_rate': round(100 * last['successful'] / last['total'], 1) if last and last['total'] else None})
    return items

@app.get('/workflows/{item_id}')
def workflow(item_id: str):
    return require('workflow', item_id)

@app.put('/workflows/{item_id}')
def edit_workflow(item_id: str, plan: Workflow):
    item = require('workflow', item_id)
    validate_columns(require('dataset', item['dataset_id']), plan.input_columns, plan.destination_column)
    if any(plan.model_dump().get(k) != Workflow.model_validate(item['plan']).model_dump().get(k) for k in ('input_columns', 'destination_column', 'mode', 'expected_column', 'status_column')):
        raise HTTPException(422, 'Record another example to change the column mapping')
    item.update(plan=plan.model_dump(), confirmed=False, human_corrections=item['human_corrections'] + 1)
    return store.put('workflow', item)

@app.post('/workflows/{item_id}/confirm')
def confirm(item_id: str):
    item = require('workflow', item_id)
    Workflow.model_validate(item['plan'])
    item['confirmed'] = True
    return store.put('workflow', item)

@app.post('/workflows/{item_id}/save')
def save_workflow(item_id: str):
    item = require('workflow', item_id)
    if not item['confirmed']:
        raise HTTPException(409, 'Confirm the workflow before saving it')
    item['saved'] = True
    return store.put('workflow', item)

@app.post('/runs')
def create_run(request: RunRequest):
    with executor.LOCK:
        workflow = require('workflow', request.workflow_id)
        if not workflow['confirmed']:
            raise HTTPException(409, 'Explicitly confirm the workflow before execution')
        if any(r['state'] in ('running', 'paused') for r in store.listing('run')):
            raise HTTPException(409, 'Finish or stop the existing run before starting another')
        dataset = require('dataset', request.dataset_id)
        plan = Workflow.model_validate(workflow['plan'])
        validate_test_columns(dataset, plan)
        validate_columns(dataset, plan.input_columns, plan.destination_column)
        run = store.put('run', {'id': store.uid(), 'workflow_id': workflow['id'], 'dataset_id': dataset['id'], 'plan': plan.model_dump(), 'state': 'running', 'total': len(dataset['rows']), 'created_at': store.now(), 'finished_at': None, 'retries': 0, 'retrying': False, 'error': '', 'demonstrations': len(workflow['demo_ids']), 'human_corrections': 0})
        # Completed teaching examples belong to this exact dataset only.
        if not developer(plan) and workflow['dataset_id'] == dataset['id']:
            first_occurrence = {}
            for index, row in enumerate(dataset['rows']):
                key = row_key(row, plan.input_columns)
                first_occurrence.setdefault(key, index)
            for demo_id in workflow['demo_ids']:
                demo = require('demo', demo_id)
                key = row_key(dataset['rows'][demo['row_index']], plan.input_columns)
                if first_occurrence[key] == demo['row_index']:
                    if demo['result'] == 'Not Found':
                        store.checkpoint(run['id'], demo['row_index'], 'manual_review', reason='Not Found', source='demonstration')
                    else:
                        store.checkpoint(run['id'], demo['row_index'], 'successful', value=demo['result'], source='demonstration')
        executor.start(run['id'])
        return executor.summary(run)

@app.get('/runs')
def runs():
    return [executor.summary(r) for r in store.listing('run')]

@app.get('/runs/{item_id}')
def run(item_id: str):
    return executor.summary(require('run', item_id))

@app.post('/runs/{item_id}/{command}')
def control_run(item_id: str, command: str):
    if command not in ('pause', 'resume', 'stop'):
        raise HTTPException(404, 'Unknown run control')
    with executor.LOCK:
        item = require('run', item_id)
        if item['state'] not in ('running', 'paused'):
            raise HTTPException(409, 'This run has already ended')
        if command == 'resume' and item['state'] != 'paused':
            raise HTTPException(409, 'Only paused runs can resume')
        item['state'] = {'pause': 'paused', 'resume': 'running', 'stop': 'stopped'}[command]
        if command == 'stop':
            item['finished_at'] = store.now()
        item['error'] = ''
        store.put('run', item)
        if command == 'resume':
            executor.start(item_id)
        return executor.summary(item)

@app.get('/runs/{item_id}/exceptions')
def exceptions(item_id: str):
    require('run', item_id)
    return [r for r in store.results(item_id) if r['status'] not in ('successful', 'PASS', 'FAIL')]

@app.put('/runs/{item_id}/exceptions/{index}')
def resolve(item_id: str, index: int, request: Resolution):
    item = require('run', item_id)
    if item['state'] not in ('completed', 'stopped'):
        raise HTTPException(409, 'Finish or stop the run before resolving exceptions')
    if developer(item['plan']):
        raise HTTPException(409, 'Rerun developer tests to verify a fix; test outcomes cannot be manually overridden')
    previous = next((r for r in store.results(item_id) if r['row_index'] == index and r['status'] != 'successful'), None)
    if not previous:
        raise HTTPException(404, 'Exception not found')
    store.checkpoint(item_id, index, 'successful', value=request.value, reason='Human reviewed', retries=previous['retries'], seconds=previous['seconds'], source='human')
    item['human_corrections'] += 1
    store.put('run', item)
    return {'ok': True}

@app.get('/runs/{item_id}/download')
def download(item_id: str):
    item = require('run', item_id)
    data = export_sheet(require('dataset', item['dataset_id']), item['plan']['destination_column'], store.results(item_id), item['plan'].get('status_column'))
    return StreamingResponse(io.BytesIO(data), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="watchmywork-results.xlsx"'})

@app.get('/metrics')
def metrics():
    with store.connect() as db:
        calls = [dict(r) for r in db.execute('SELECT * FROM inference')]
    output = []
    for workflow in store.listing('workflow'):
        history = [executor.summary(r) for r in store.listing('run') if r['workflow_id'] == workflow['id']]
        related = [c for c in calls if c['workflow_id'] == workflow['id']]
        output.append({'workflow_id': workflow['id'], 'number_of_demonstrations': len(workflow['demo_ids']), 'ai_inference_latency': sum(c['latency'] for c in related), 'ai_call_count': len(related), 'human_corrections': workflow['human_corrections'] + sum(r['human_corrections'] for r in history), 'records_processed': sum(r['processed'] for r in history), 'successes': sum(r['successful'] for r in history), 'failures': sum(r['failed'] for r in history), 'retries': sum(r['retries'] for r in history), 'manual_reviews': sum(r['manual_review'] for r in history), 'total_execution_time': round(sum(r['seconds'] for r in history), 3), 'average_execution_time_per_record': round(sum(r['seconds'] for r in history) / max(1, sum(r['processed'] for r in history)), 3)})
    return {'workflows': output, 'inference_attempts': calls, 'total_ai_calls': len(calls)}

@app.get('/metrics/download')
def download_metrics():
    return JSONResponse(metrics(), headers={'Content-Disposition': 'attachment; filename="watchmywork-metrics.json"'})

@app.get('/dashboard')
def dashboard():
    history = runs()
    return {'workflows_created': len([w for w in store.listing('workflow') if w['confirmed']]), 'records_processed': sum(r['processed'] for r in history), 'successful_automations': sum(r['successful'] for r in history), 'manual_review_items': sum(r['manual_review'] for r in history), 'recent_workflows': workflows()[:5], 'recent_runs': history[:5]}

@app.get('/samples/developer')
def developer_sample():
    return FileResponse(Path(__file__).resolve().parents[1] / 'sample-data/developer-tests.csv', filename='developer-tests.csv')

@app.get('/workflows/{item_id}/generated-test')
def generated_test(item_id: str):
    from .developer import generate
    item = require('workflow', item_id)
    if not item['confirmed'] or not developer(item['plan']):
        raise HTTPException(409, 'Confirm a developer test workflow first')
    return {'code': generate(item['plan']), 'filename': 'generated_test.spec.py'}

@app.get('/workflows/{item_id}/test-download')
def test_download(item_id: str, dataset_id: str | None = None):
    import zipfile
    item = require('workflow', item_id)
    code = generated_test(item_id)['code']
    dataset = require('dataset', dataset_id or item['dataset_id'])
    plan = Workflow.model_validate(item['plan'])
    validate_columns(dataset, plan.input_columns, plan.destination_column)
    validate_test_columns(dataset, plan)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('generated_test.spec.py', code)
        archive.writestr('test_cases.json', json.dumps(dataset['rows'], indent=2))
    return StreamingResponse(io.BytesIO(out.getvalue()), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="playwright-test.zip"'})

@app.get('/runs/{item_id}/test-report')
def test_report(item_id: str):
    from .developer import report
    item = require('run', item_id)
    if not developer(item['plan']):
        return []
    return report(item, require('dataset', item['dataset_id']), store.results(item_id))

@app.post('/runs/{item_id}/debug/package')
def bob_package(item_id: str):
    from .developer import package
    item = require('run', item_id)
    if not developer(item['plan']) or item['state'] not in ('completed', 'stopped'):
        raise HTTPException(409, 'Finish the developer test run first')
    return {'path': package(item, require('dataset', item['dataset_id']), store.results(item_id))}


# Register static routes after API routes. No catch-all: unknown API/private paths
# remain 404, and only built assets are served (never source or runtime storage).
if config.PRODUCTION:
    app.mount('/assets', StaticFiles(directory=config.FRONTEND_DIST / 'assets'), name='frontend-assets')
    app.mount('/demo-static/assets', StaticFiles(directory=config.DEMO_DIST / 'assets'), name='demo-assets')

    @app.get('/', include_in_schema=False)
    def frontend_page():
        return FileResponse(config.FRONTEND_DIST / 'index.html')

    @app.get('/developer', include_in_schema=False)
    @app.get('/weather', include_in_schema=False)
    def demo_page():
        return FileResponse(config.DEMO_DIST / 'index.html')
