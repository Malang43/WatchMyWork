import asyncio
import json
import httpx
import pytest
from backend import inference, storage
from backend.schema import demonstrated_plan

@pytest.mark.parametrize('failure', ['timeout', 'connection', 408, 429, 500, 502, 503, 504])
def test_retry_then_success(client, recorded, dataset, monkeypatch, failure, capsys):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-placeholder')
    calls, delays, progress = [], [], []
    async def sleep(delay): delays.append(delay)
    monkeypatch.setattr(inference.asyncio, 'sleep', sleep)
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            if failure == 'timeout': raise httpx.ReadTimeout('private provider detail')
            if failure == 'connection': raise httpx.ConnectError('private provider detail')
            return httpx.Response(failure)
        return httpx.Response(200, json={'choices': [{'message': {'content': demonstrated_plan('Tracking ID', 'Status').model_dump_json()}}]})
    original = httpx.AsyncClient
    def factory(**kwargs):
        assert kwargs['timeout'].read == 120 and kwargs['timeout'].connect == 120
        return original(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(inference.httpx, 'AsyncClient', factory)
    before = storage.get('demo', recorded['id'])
    plan, _ = asyncio.run(inference.infer([before], 'Tracking ID', 'Status', dataset['id'], progress.append))
    assert plan.input_columns == ['Tracking ID']
    assert len(calls) == 2 and delays == [2] and progress == [1, 2]
    assert storage.get('demo', recorded['id']) == before
    logs = capsys.readouterr().out
    assert 'Nemotron attempt 2/3' in logs and 'Nemotron success' in logs
    assert 'unit-test-placeholder' not in logs and 'private provider detail' not in logs

def test_all_fail_compiles_weather_and_requires_confirmation(client, monkeypatch, capsys):
    from backend.tests.test_weather import weather_demo, events, COLS, OUT
    dataset, mapping, demo = weather_demo(client)
    client.post(f"/demos/{demo['id']}/events", json={'events': events()})
    before = storage.get('demo', demo['id'])
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-placeholder')
    calls, delays, statuses = [], [], []
    async def sleep(delay): delays.append(delay)
    monkeypatch.setattr(inference.asyncio, 'sleep', sleep)
    def handler(request):
        calls.append(1)
        from backend.main import INFER_PROGRESS
        statuses.append(INFER_PROGRESS[dataset['id']]['attempt'])
        raise httpx.ReadTimeout('private provider detail')
    original = httpx.AsyncClient
    monkeypatch.setattr(inference.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    response = client.post('/workflows/infer', json=mapping)
    assert response.status_code == 200, response.text
    workflow = response.json()
    assert len(calls) == 3 and delays == [2, 5] and statuses == [1, 2, 3]
    assert workflow['source'] == 'semantic_fallback' and not workflow['confirmed']
    assert workflow['plan']['input_columns'] == COLS and workflow['plan']['destination_column'] == OUT
    assert [s['target'] for s in workflow['plan']['steps'][:-1]] == [e['target'] for e in events()]
    assert [s['value'] for s in workflow['plan']['steps'][:2]] == ['{{row.Latitude}}', '{{row.Longitude}}']
    assert storage.get('demo', demo['id']) == before
    assert client.post('/runs', json={'workflow_id': workflow['id'], 'dataset_id': dataset['id']}).status_code == 409
    metrics = client.get('/metrics').json()
    assert metrics['total_ai_calls'] == 3
    assert metrics['workflows'][0]['ai_call_count'] == 3
    logs = capsys.readouterr().out
    assert 'Nemotron unavailable after 3 attempts' in logs and 'Using semantic workflow fallback' in logs
    assert 'unit-test-placeholder' not in logs and 'private provider detail' not in logs

@pytest.mark.parametrize('status', [400, 401, 403, 404, 422, 501])
def test_non_retryable_response_preserves_demo(client, recorded, dataset, monkeypatch, status):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-placeholder')
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(status)
    original = httpx.AsyncClient
    monkeypatch.setattr(inference.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    before = storage.get('demo', recorded['id'])
    response = client.post('/workflows/infer', json={'dataset_id': dataset['id'], 'input_column': 'Tracking ID', 'destination_column': 'Status'})
    assert response.status_code == 503 and len(calls) == 1
    assert storage.get('demo', recorded['id']) == before
    assert storage.listing('workflow') == []

def test_compiler_rejects_missing_or_unsafe_observed_step(client, monkeypatch):
    from backend.tests.test_weather import weather_demo, events, COLS, OUT
    _, _, demo = weather_demo(client)
    client.post(f"/demos/{demo['id']}/events", json={'events': events()})
    saved = storage.get('demo', demo['id'])
    saved['events'] = [e for e in saved['events'] if e['action'] != 'wait']
    with pytest.raises(inference.InferenceError, match='compiled safely'):
        inference.compile_demonstration([saved], COLS, OUT)
    saved['events'] = events()
    saved['events'][2]['target'] = '#unobserved-button'
    with pytest.raises(inference.InferenceError, match='compiled safely'):
        inference.compile_demonstration([saved], COLS, OUT)

@pytest.mark.parametrize('kind', ['valid', 'malformed', 'unsafe', 'timeout', 'rate_limit'])
def test_inference_validation_and_metrics(client, recorded, dataset, monkeypatch, kind):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-placeholder')
    monkeypatch.setattr(inference, 'RETRY_DELAYS', (0, 0))
    demo = storage.get('demo', recorded['id'])
    plan = demonstrated_plan('Tracking ID', 'Status').model_dump()
    if kind == 'unsafe': plan['url'] = 'https://example.com/'
    def handler(request):
        payload = json.loads(request.content)
        assert payload['model'] == 'nvidia/nemotron-3.5-lightning:free'
        assert 'PK100001' not in str(payload) and 'Delivered' not in str(payload)
        if kind == 'timeout': raise httpx.ReadTimeout('simulated')
        if kind == 'rate_limit': return httpx.Response(429)
        return httpx.Response(200, json={'choices': [{'message': {'content': 'not json' if kind == 'malformed' else json.dumps(plan)}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(inference.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    if kind == 'valid':
        result, _ = asyncio.run(inference.infer([demo], 'Tracking ID', 'Status', dataset['id']))
        assert result.input_column == 'Tracking ID'
    else:
        with pytest.raises(inference.InferenceError): asyncio.run(inference.infer([demo], 'Tracking ID', 'Status', dataset['id']))
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM inference').fetchone()[0] == (3 if kind in ('timeout', 'rate_limit') else 1)

def test_total_deadline_even_if_provider_keeps_connection_open(client, recorded, dataset, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-placeholder')
    monkeypatch.setattr(inference, 'RETRY_DELAYS', (0, 0))
    monkeypatch.setattr(inference, 'INFERENCE_TIMEOUT', .02)
    class SlowClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): await asyncio.sleep(10)
    monkeypatch.setattr(inference.httpx, 'AsyncClient', lambda **kwargs: SlowClient())
    with pytest.raises(inference.InferenceError, match='temporarily unavailable'):
        asyncio.run(inference.infer([storage.get('demo', recorded['id'])], 'Tracking ID', 'Status', dataset['id']))
    with storage.connect() as db:
        row = db.execute('SELECT success,latency FROM inference').fetchone()
        assert row['success'] == 0 and row['latency'] < 1
