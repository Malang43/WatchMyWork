from fastapi.testclient import TestClient
from backend import storage, executor, recovery, config
from backend.main import app


def test_confirmation_saves_and_survives_restart(client, workflow, monkeypatch):
    wid = workflow['id']
    saved = client.post(f'/workflows/{wid}/confirm').json()
    assert saved['saved'] and saved['confirmed']
    assert saved['created_at'] and saved['updated_at']
    assert saved['demo_ids'] == workflow['demo_ids']
    assert storage.get('demo', saved['demo_ids'][0])['events']
    # New application lifespan and SQLite connections, no frontend/session state.
    with TestClient(app, headers={'X-WatchMyWork': 'local-demo'}) as fresh:
        loaded = fresh.get(f'/workflows/{wid}').json()
        assert loaded == saved
        assert fresh.get('/workflows?saved_only=true').json()[0]['id'] == wid
        monkeypatch.setattr(executor, 'start', lambda _: None)
        response = fresh.post('/runs', json={'workflow_id': wid, 'dataset_id': loaded['dataset_id']})
        assert response.status_code == 200
        assert response.json()['plan'] == loaded['plan']


def test_existing_confirmed_workflow_becomes_visible(client, workflow):
    legacy = {**workflow, 'confirmed': True, 'saved': False}
    legacy.pop('updated_at', None)
    storage.put('workflow', legacy)
    storage.init()
    restored = storage.get('workflow', legacy['id'])
    assert restored['saved'] and restored['updated_at'] == legacy['created_at']
    assert restored['plan'] == legacy['plan']
    assert restored['demo_ids'] == legacy['demo_ids']
    storage.init()
    assert storage.get('workflow', legacy['id']) == restored


def test_saved_edit_remains_visible_but_requires_confirmation(client, workflow, monkeypatch):
    wid = workflow['id']
    client.post(f'/workflows/{wid}/confirm')
    plan = {**workflow['plan'], 'workflow_name': 'Updated workflow'}
    changed = client.put(f'/workflows/{wid}', json=plan).json()
    assert changed['saved'] and not changed['confirmed']
    assert changed['updated_at']
    assert client.get('/workflows?saved_only=true').json()[0]['plan']['workflow_name'] == 'Updated workflow'
    assert client.post('/runs', json={'workflow_id': wid, 'dataset_id': workflow['dataset_id']}).status_code == 409
    assert client.post(f'/workflows/{wid}/confirm').json()['confirmed']


def test_saved_filter_preserves_existing_listing(client, workflow):
    assert client.get('/workflows?saved_only=true').json() == []
    assert client.get('/workflows').json()[0]['id'] == workflow['id']


def test_only_exact_developer_demo_query_allowed():
    url = config.DEVELOPER_URL
    assert recovery.safe_navigation(url + '?recovery_demo=1', url)
    for suffix in ('?recovery_demo=0', '?recovery_demo=1&other=1', '?other=1', '?recovery_demo=1#x'):
        assert not recovery.safe_navigation(url + suffix, url)
    assert not recovery.safe_navigation(config.WEATHER_URL + '?recovery_demo=1', config.WEATHER_URL)
