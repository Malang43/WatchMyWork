import pytest
from fastapi.testclient import TestClient
from backend import storage
from backend.main import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    with TestClient(app, headers={'X-WatchMyWork': 'local-demo'}) as client:
        yield client

@pytest.fixture
def dataset(client):
    response = client.post('/datasets', files={'file': ('test.csv', b'Tracking ID,Status\nPK100001,\nPK100002,\nPK100001,\n,\n', 'text/csv')})
    assert response.status_code == 200
    return response.json()

@pytest.fixture
def recorded(client, dataset):
    request = {'dataset_id': dataset['id'], 'row_index': 0, 'input_column': 'Tracking ID', 'destination_column': 'Status'}
    demo = client.post('/demos', json=request).json()
    events = [{'action': 'fill', 'target': '#tracking-id', 'value': 'PK100001'}, {'action': 'click', 'target': 'button[type="submit"]'}, {'action': 'extract', 'target': '#tracking-result .status', 'text': 'Delivered'}]
    assert client.post(f"/demos/{demo['id']}/events", json={'events': events}).status_code == 200
    assert client.post(f"/demos/{demo['id']}/stop").json()['state'] == 'complete'
    return demo

@pytest.fixture
def workflow(client, dataset, recorded):
    return client.post('/workflows/manual', json={'dataset_id': dataset['id'], 'input_column': 'Tracking ID', 'destination_column': 'Status'}).json()
