import re
import threading
import time
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout, Error as BrowserError
from . import storage as store, config
from .schema import Workflow, MOCK_URL, row_key, valid_coordinates, valid_temperature, developer

LOCK = threading.RLock()
WORKERS = {}
STATUSES = {'Delivered', 'Pending', 'In Transit', 'Returned', 'Not Found'}

def allowed_url(url, weather=False):
    parts = urlparse(url)
    if weather and parts.scheme == 'https' and parts.hostname == 'api.open-meteo.com' and parts.port in (None, 443) and parts.path == '/v1/forecast' and not parts.username and not parts.password:
        query = parse_qs(parts.query)
        return set(query) == {'latitude', 'longitude', 'current'} and query['current'] == ['temperature_2m'] and len(query['latitude']) == len(query['longitude']) == 1 and valid_coordinates([query['latitude'][0], query['longitude'][0]])
    if config.PRODUCTION:
        return bool(config.PUBLIC_ORIGIN) and urlparse(config.PUBLIC_ORIGIN).netloc == parts.netloc and parts.scheme == 'https' and not parts.username and not parts.password and (parts.path in ('/developer', '/weather') or parts.path.startswith('/demo-static/assets/'))
    return parts.scheme in ('http', 'ws') and parts.hostname == '127.0.0.1' and parts.port == 5173 and not parts.username and not parts.password

def start(run_id):
    with LOCK:
        if run_id in WORKERS and WORKERS[run_id].is_alive():
            return
        thread = threading.Thread(target=execute, args=(run_id,), daemon=True, name='watchmywork-executor')
        WORKERS[run_id] = thread
        thread.start()

def update_state(run_id, state, **fields):
    with LOCK:
        run = store.get('run', run_id)
        run.update(state=state, **fields)
        store.put('run', run)

def wait_for_permission(run_id):
    while True:
        run = store.get('run', run_id)
        if run['state'] == 'stopped':
            return False
        if run['state'] != 'paused':
            return True
        time.sleep(.15)

def set_retrying(run_id, value):
    with LOCK:
        run = store.get('run', run_id)
        run['retrying'] = value
        store.put('run', run)

def execute(run_id):
    run = store.get('run', run_id)
    dataset = store.get('dataset', run['dataset_id'])
    plan = Workflow.model_validate(run['plan'])
    dev = developer(plan)
    weather = len(plan.input_columns) == 2 and not dev
    completed = {r['row_index']: r for r in store.results(run_id)}
    seen = set()
    try:
        with sync_playwright() as pw:
            browser = None
            page = None
            try:
                for index, row in enumerate(dataset['rows']):
                    values = [row[column].strip() for column in plan.input_columns]
                    key = row_key(row, plan.input_columns)
                    duplicate = key in seen
                    if key:
                        seen.add(key)
                    if index in completed:
                        continue
                    if not wait_for_permission(run_id):
                        return
                    started = time.monotonic()
                    if not dev and any(not value for value in values):
                        store.checkpoint(run_id, index, 'manual_review', reason='Blank input')
                        continue
                    if not dev and duplicate:
                        store.checkpoint(run_id, index, 'manual_review', reason='Duplicate coordinates; verify this row explicitly' if weather else 'Duplicate ID; verify this row explicitly')
                        continue
                    if not dev and ((not valid_coordinates(values)) if weather else (not re.fullmatch(r'PK\d{6}', values[0].upper()))):
                        store.checkpoint(run_id, index, 'manual_review', reason='Invalid coordinates' if weather else 'Invalid tracking ID format')
                        continue
                    for attempt in range(2):
                        if not wait_for_permission(run_id):
                            return
                        stage = 'browser'
                        try:
                            if browser is None or not browser.is_connected():
                                browser = pw.chromium.launch(headless=True)
                                context = browser.new_context(service_workers='block')
                                context.route('**/*', lambda route: route.continue_() if allowed_url(route.request.url, weather) else route.abort())
                                page = context.new_page()
                                page.set_default_timeout(7000)
                            if page is None or page.is_closed():
                                page = browser.contexts[0].new_page()
                                page.set_default_timeout(7000)
                            page.goto(plan.url, wait_until='domcontentloaded', timeout=10000)
                            if page.url != plan.url:
                                raise BrowserError('Unexpected navigation')
                            for index_of_input, column in enumerate(plan.input_columns):
                                page.locator(plan.steps[index_of_input].target).fill(row[column] if dev else row[column].strip() if weather else row[column].strip().upper())
                            page.locator(plan.steps[len(plan.input_columns)].target).click()
                            stage = 'result'
                            result = page.locator(plan.steps[-2].target)
                            if weather:
                                page.wait_for_function("['success', 'error'].includes(document.querySelector('#weather-result')?.dataset.state)", timeout=15000)
                                if page.locator('#weather-result').get_attribute('data-state') == 'error':
                                    raise BrowserTimeout('Weather request failed')
                                page.locator(plan.steps[3].target).wait_for(state='visible', timeout=15000)
                            else:
                                result.wait_for(state='visible')
                            value = result.inner_text() if dev else result.inner_text().strip()
                            if dev:
                                passed = value.strip().casefold() == row[plan.expected_column].strip().casefold()
                                store.checkpoint(run_id, index, 'PASS' if passed else 'FAIL', value=value, reason='' if passed else 'Expected and actual results differ', retries=attempt, seconds=time.monotonic() - started)
                                break
                            if (not valid_temperature(value)) if weather else (value not in STATUSES or value == 'Not Found'):
                                store.checkpoint(run_id, index, 'manual_review', reason='Not Found' if value == 'Not Found' else 'Unrecognized or missing result', retries=attempt, seconds=time.monotonic() - started)
                            else:
                                store.checkpoint(run_id, index, 'successful', value=value, retries=attempt, seconds=time.monotonic() - started)
                            break
                        except (BrowserTimeout, BrowserError):
                            if attempt == 0:
                                set_retrying(run_id, True)
                                with LOCK:
                                    current = store.get('run', run_id)
                                    current['retries'] += 1
                                    store.put('run', current)
                                time.sleep(.25)
                            else:
                                store.checkpoint(run_id, index, 'ERROR' if dev else 'manual_review' if stage == 'result' else 'failed', reason='Result missing after retry' if stage == 'result' else 'Website timeout, missing selector, or browser unavailable', retries=1, seconds=time.monotonic() - started)
                        finally:
                            set_retrying(run_id, False)
                with LOCK:
                    current = store.get('run', run_id)
                    if current['state'] != 'stopped':
                        update_state(run_id, 'completed', finished_at=store.now(), retrying=False)
            finally:
                if browser and browser.is_connected():
                    browser.close()
    except Exception:
        # An unexpected worker failure never discards committed results.
        update_state(run_id, 'paused', error='Execution was interrupted. Completed rows are saved. Resume to retry the remaining rows.', retrying=False)
    finally:
        with LOCK:
            WORKERS.pop(run_id, None)
            # A resume can arrive just as an interrupted worker exits.
            current = store.get('run', run_id)
            if current and current['state'] == 'running':
                start(run_id)

def summary(run):
    outcomes = store.results(run['id'])
    counts = {status: sum(r['status'] == status for r in outcomes) for status in ['successful', 'failed', 'manual_review', 'PASS', 'FAIL', 'ERROR']}
    if developer(run['plan']):
        counts['successful'] = counts['PASS']
        counts['failed'] = counts['FAIL']
    elapsed = sum(r['seconds'] for r in outcomes)
    return {**run, **counts, 'processed': len(outcomes), 'seconds': round(elapsed, 2), 'average_seconds': round(elapsed / len(outcomes), 3) if outcomes else 0}
