import json
import asyncio
import httpx
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError
from backend import executor, storage, inference
from backend.inference import evidence
from backend.schema import Workflow, demonstrated_plan

COLS = ['Latitude', 'Longitude']
OUT = 'Current Temperature (°C)'

def weather_demo(client):
    data = client.post('/datasets', files={'file': ('weather.csv', f'Latitude,Longitude,{OUT}\n33.6844,73.0479,\n33.6844,67.0011,\n51.5074,-0.1278,\n'.encode(), 'text/csv')}).json()
    mapping = {'dataset_id': data['id'], 'input_columns': COLS, 'destination_column': OUT}
    demo = client.post('/demos', json={**mapping, 'row_index': 0}).json()
    return data, mapping, demo

def events(longitude='73.0479'):
    return [
        {'action': 'fill', 'target': '#latitude-input', 'value': '33.6844'},
        {'action': 'fill', 'target': '#longitude-input', 'value': longitude},
        {'action': 'click', 'target': '#check-weather-button'},
        {'action': 'wait', 'target': '#temperature-result'},
        {'action': 'extract', 'target': '#temperature-result', 'text': '0 °C'},
    ]

def test_autosave_and_private_independent_bindings(client, monkeypatch):
    data, mapping, demo = weather_demo(client)
    current = client.get('/teach/current').json()
    assert current['input_columns'] == COLS
    assert current['bindings'] == {'#latitude-input': 'Latitude', '#longitude-input': 'Longitude'}
    assert client.post(f"/demos/{demo['id']}/events", json={'events': events()}).json()['state'] == 'complete'
    assert client.get('/teach/current').json() is None
    saved = client.get('/demos', params={'dataset_id': data['id']}).json()[0]
    sanitized = json.dumps(evidence([saved], COLS, OUT))
    assert '{{row.Latitude}}' in sanitized and '{{row.Longitude}}' in sanitized
    assert '33.6844' not in sanitized and '73.0479' not in sanitized and '0 °C' not in sanitized
    workflow = client.post('/workflows/manual', json=mapping).json()
    run_request = {'workflow_id': workflow['id'], 'dataset_id': data['id']}
    assert client.post('/runs', json=run_request).status_code == 409
    client.post(f"/workflows/{workflow['id']}/confirm")
    monkeypatch.setattr(executor, 'start', lambda _: None)
    run = client.post('/runs', json=run_request).json()
    assert run['processed'] == 1 and run['successful'] == 1
    assert storage.results(run['id'])[0]['value'] == '0 °C'

@pytest.mark.parametrize('change', ['missing_longitude', 'wrong_longitude', 'missing_wait', 'bad_result'])
def test_incomplete_weather_never_autosaves(client, change):
    _, mapping, demo = weather_demo(client)
    batch = events()
    if change == 'missing_longitude': del batch[1]
    if change == 'wrong_longitude': batch[1]['value'] = '67'
    if change == 'missing_wait': del batch[3]
    if change == 'bad_result': batch[-1]['text'] = 'not a temperature'
    assert client.post(f"/demos/{demo['id']}/events", json={'events': batch}).json()['state'] == 'recording'
    assert client.post('/workflows/manual', json=mapping).status_code == 422

def test_schema_legacy_and_fixed_value_rejection():
    legacy = demonstrated_plan('Tracking ID', 'Status').model_dump()
    del legacy['input_columns']
    assert Workflow.model_validate(legacy).input_columns == ['Tracking ID']
    plan = demonstrated_plan(COLS, OUT).model_dump()
    assert [s['action'] for s in plan['steps']] == ['fill', 'fill', 'click', 'wait', 'extract', 'write_spreadsheet']
    plan['steps'][1]['value'] = '73.0479'
    with pytest.raises(ValidationError): Workflow.model_validate(plan)

def test_weather_executor_pair_duplicates_and_row_binding(client, monkeypatch):
    data, _, _ = weather_demo(client)
    dataset = storage.get('dataset', data['id'])
    dataset['rows'] += [dataset['rows'][0].copy(), {'Latitude': '', 'Longitude': '1', OUT: ''}, {'Latitude': '91', 'Longitude': '1', OUT: ''}]
    storage.put('dataset', dataset)
    run = storage.put('run', {'id': storage.uid(), 'dataset_id': data['id'], 'plan': demonstrated_plan(COLS, OUT).model_dump(), 'state': 'running', 'retries': 0, 'retrying': False})
    manager = MagicMock()
    browser = manager.__enter__.return_value.chromium.launch.return_value
    browser.is_connected.return_value = True
    page = browser.new_context.return_value.new_page.return_value
    page.is_closed.return_value = False
    page.url = 'http://127.0.0.1:5173/'
    elements = {s: MagicMock() for s in ['#latitude-input', '#longitude-input', '#check-weather-button', '#weather-result', '#temperature-result']}
    page.locator.side_effect = elements.__getitem__
    elements['#weather-result'].get_attribute.return_value = 'success'
    elements['#temperature-result'].inner_text.side_effect = ['25 °C', '29 °C', '12 °C']
    monkeypatch.setattr(executor, 'sync_playwright', lambda: manager)
    executor.execute(run['id'])
    results = storage.results(run['id'])
    assert [r['status'] for r in results] == ['successful'] * 3 + ['manual_review'] * 3
    assert [c.args[0] for c in elements['#longitude-input'].fill.call_args_list] == ['73.0479', '67.0011', '-0.1278']
    assert [r['value'] for r in results[:3]] == ['25 °C', '29 °C', '12 °C']
    assert elements['#temperature-result'].wait_for.call_count == 3

def test_weather_network_boundary():
    url = 'https://api.open-meteo.com/v1/forecast?latitude=33.6844&longitude=73.0479&current=temperature_2m'
    assert executor.allowed_url(url, weather=True)
    assert not executor.allowed_url(url)
    assert not executor.allowed_url(url.replace('api.open-meteo.com', 'example.com'), weather=True)
    assert not executor.allowed_url(url + '&secret=anything', weather=True)
    assert not executor.allowed_url(url.replace('33.6844', '91'), weather=True)

def test_weather_inference_two_variables(client, monkeypatch):
    data, _, demo = weather_demo(client)
    client.post(f"/demos/{demo['id']}/events", json={'events': events()})
    saved = storage.get('demo', demo['id'])
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-placeholder')
    def handler(request):
        payload = json.loads(request.content)
        prompt = json.loads(payload['messages'][1]['content'])
        assert prompt['input_columns'] == COLS
        fills = [e for e in prompt['demonstrations'][0]['events'] if e['action'] == 'fill']
        assert [(e['target'], e['value']) for e in fills] == [('#latitude-input', '{{row.Latitude}}'), ('#longitude-input', '{{row.Longitude}}')]
        assert '33.6844' not in str(payload) and '73.0479' not in str(payload)
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(demonstrated_plan(COLS, OUT).model_dump())}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(inference.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    plan, _ = asyncio.run(inference.infer([saved], COLS, OUT, data['id']))
    assert plan.input_columns == COLS
