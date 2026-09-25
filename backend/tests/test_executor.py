from unittest.mock import MagicMock
import pytest
from playwright.sync_api import Error as BrowserError, TimeoutError as BrowserTimeout
from backend import executor, storage
from backend.schema import demonstrated_plan

def setup_run(rows):
    dataset = storage.put('dataset', {'id': storage.uid(), 'columns': ['Tracking ID', 'Status'], 'rows': [{'Tracking ID': value, 'Status': ''} for value in rows]})
    return storage.put('run', {'id': storage.uid(), 'dataset_id': dataset['id'], 'plan': demonstrated_plan('Tracking ID', 'Status').model_dump(), 'state': 'running', 'retries': 0, 'retrying': False})

def browser_fixture(monkeypatch):
    manager = MagicMock()
    pw = manager.__enter__.return_value
    browser = pw.chromium.launch.return_value
    browser.is_connected.return_value = True
    page = browser.new_context.return_value.new_page.return_value
    page.url = 'http://127.0.0.1:5173/'
    page.is_closed.return_value = False
    page.locator.return_value.inner_text.return_value = 'Delivered'
    monkeypatch.setattr(executor, 'sync_playwright', lambda: manager)
    return page

def test_retry_then_success_and_special_inputs(client, monkeypatch):
    page = browser_fixture(monkeypatch)
    page.goto.side_effect = [BrowserTimeout('transient'), None]
    run = setup_run(['PK100001', 'PK100001', '', 'bad'])
    executor.execute(run['id'])
    results = storage.results(run['id'])
    assert [r['status'] for r in results] == ['successful', 'manual_review', 'manual_review', 'manual_review']
    assert storage.get('run', run['id'])['retries'] == 1
    assert storage.get('run', run['id'])['state'] == 'completed'
    assert page.goto.call_count == 2

@pytest.mark.parametrize('kind,status', [('browser', 'failed'), ('result', 'manual_review')])
def test_browser_failure_and_missing_result_checkpoint(client, monkeypatch, kind, status):
    page = browser_fixture(monkeypatch)
    if kind == 'browser': page.goto.side_effect = BrowserError('closed')
    else: page.locator.return_value.wait_for.side_effect = BrowserTimeout('missing result')
    run = setup_run(['PK100001'])
    executor.execute(run['id'])
    result = storage.results(run['id'])[0]
    assert result['status'] == status and result['retries'] == 1

def test_resume_skips_checkpointed_rows(client, monkeypatch):
    page = browser_fixture(monkeypatch)
    run = setup_run(['PK100001', 'PK100002'])
    storage.checkpoint(run['id'], 0, 'successful', value='Delivered')
    executor.execute(run['id'])
    assert page.goto.call_count == 1
    assert len(storage.results(run['id'])) == 2

def test_stopped_worker_does_not_touch_browser(client, monkeypatch):
    page = browser_fixture(monkeypatch)
    run = setup_run(['PK100001'])
    run['state'] = 'stopped'
    storage.put('run', run)
    executor.execute(run['id'])
    page.goto.assert_not_called()
    assert storage.results(run['id']) == []
