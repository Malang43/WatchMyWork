"""Production configuration is tested in isolation from the local app/database."""
import os
import subprocess
import sys


def test_production_routes_storage_and_boundaries(tmp_path):
    script = r'''
import os
from pathlib import Path
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend import config
root = Path(os.environ['TEST_ROOT'])
for name in ('frontend', 'demo'):
    folder = root / name
    (folder / 'assets').mkdir(parents=True)
    (folder / 'index.html').write_text('<html>' + name + '</html>')
    (folder / 'assets' / 'app.js').write_text('// ' + name)
config.FRONTEND_DIST = root / 'frontend'
config.DEMO_DIST = root / 'demo'
from backend.main import app
from backend.schema import Mapping, Event, Workflow, demonstrated_plan
from backend.executor import allowed_url
from backend import storage, developer
origin = config.PUBLIC_ORIGIN
mapping = Mapping(mode='developer', input_columns=['Email', 'Password'], destination_column='Actual', expected_column='Expected', status_column='Status')
plan = demonstrated_plan(mapping, 'Actual')
assert plan.url == origin + '/developer'
assert origin + '/developer' in developer.generate(plan.model_dump())
for bad in ('https://attacker.invalid/developer', origin + '/weather', origin + '/developer?x=1'):
    try:
        Workflow.model_validate({**plan.model_dump(), 'url': bad})
    except ValidationError:
        pass
    else:
        raise AssertionError('Unsafe workflow accepted')
try:
    Event(action='navigate', target='x', url='https://attacker.invalid/developer')
except ValidationError:
    pass
else:
    raise AssertionError('Unsafe event accepted')
assert allowed_url(origin + '/developer')
assert allowed_url(origin + '/demo-static/assets/app.js')
for bad in (origin + '/datasets', origin + '/docs', 'https://attacker.invalid/developer', 'http://127.0.0.1:5173/'):
    assert not allowed_url(bad)
assert allowed_url('https://api.open-meteo.com/v1/forecast?latitude=1&longitude=2&current=temperature_2m', True)
with TestClient(app, base_url=origin) as client:
    assert client.get('/').text == '<html>frontend</html>'
    for path in ('/developer', '/weather'):
        assert client.get(path).text == '<html>demo</html>'
    for path in ('/assets/app.js', '/demo-static/assets/app.js', '/health', '/docs', '/openapi.json'):
        assert client.get(path).status_code == 200
    for path in ('/.env', '/backend/data/watchmywork.sqlite3', '/bob_debug_package/private.json', '/missing-api', '/demo-static/assets/missing.js'):
        assert client.get(path).status_code == 404
    assert client.get('/datasets/x', headers={'Origin': 'https://attacker.invalid'}).status_code == 403
    assert client.get('/health', headers={'Host': 'healthcheck.railway.app'}).status_code == 200
    assert client.get('/datasets/x', headers={'Host': 'healthcheck.railway.app'}).status_code == 403
    assert client.post('/demos', json={}).status_code == 403
    response = client.options('/demos', headers={'Origin': 'chrome-extension://' + 'a'*32, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'X-WatchMyWork'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'chrome-extension://' + 'a'*32
    headers = {'Origin': 'chrome-extension://' + 'a'*32, 'X-WatchMyWork': 'local-demo'}
    dataset = client.post('/datasets', headers=headers, files={'file': ('production.csv', b'Email,Password,Expected,Actual,Status\ndev@example.com,test123,Login successful,,\n', 'text/csv')}).json()
    demo = client.post('/demos', headers=headers, json={**mapping.model_dump(), 'dataset_id': dataset['id'], 'row_index': 0}).json()
    assert client.get('/teach/current', headers=headers).json()['id'] == demo['id']
    events = [
        {'action': 'navigate', 'target': origin + '/developer'},
        {'action': 'fill', 'target': '#email-input', 'value': 'dev@example.com'},
        {'action': 'fill', 'target': '#password-input', 'value': 'test123'},
        {'action': 'click', 'target': '#login-button'},
        {'action': 'wait', 'target': '#login-result'},
        {'action': 'extract', 'target': '#login-result', 'text': 'Login successful'},
    ]
    response = client.post('/demos/' + demo['id'] + '/events', headers=headers, json={'events': [{**e, 'url': origin + '/developer'} for e in events]})
    assert response.status_code == 200
    assert response.json()['state'] == 'complete'
    response = client.post('/demos/' + demo['id'] + '/stop', headers=headers)
    assert response.status_code == 200 and response.json()['state'] == 'complete'
    assert client.get('/teach/current', headers=headers).json() is None
    assert client.get('/demos', params={'dataset_id': dataset['id']}).json()[0]['state'] == 'complete'
    bad = client.post('/demos/' + demo['id'] + '/events', headers=headers, json={'events': [{'action': 'navigate', 'target': 'http://127.0.0.1:5173/developer', 'url': 'http://127.0.0.1:5173/developer'}]})
    assert bad.status_code == 422
    storage.put('dataset', {'id': 'persisted', 'rows': []})
    run = {'id': 'synthetic', 'plan': plan.model_dump(), 'state': 'completed'}
    directory = developer.package(run, {'rows': []}, [])
    assert Path(directory).parent == Path(os.environ['BOB_DEBUG_DIR'])
with TestClient(app, base_url=origin):
    assert storage.get('dataset', 'persisted')['rows'] == []
assert Path(os.environ['DATABASE_PATH']).exists()
'''
    env = {**os.environ, 'WATCHMYWORK_PRODUCTION': '1', 'PUBLIC_ORIGIN': 'https://deployment.example',
           'DATABASE_PATH': str(tmp_path / 'data' / 'custom.sqlite3'),
           'BOB_DEBUG_DIR': str(tmp_path / 'data' / 'debug'), 'TEST_ROOT': str(tmp_path)}
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
