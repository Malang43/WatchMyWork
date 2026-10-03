"""Recovery tests use isolated databases and synthetic data, never live provider calls."""
import asyncio
import json
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest
from playwright.sync_api import Error as BrowserError
from backend import recovery as r, storage, executor
from backend.schema import Mapping, demonstrated_plan
from backend.tests.test_developer import MAPPING


def candidate(name='Sign In', **kw):
    return r.Candidate(id=0, selector='body > form:nth-child(1) > button:nth-child(3)', role='button', name=name, label='', placeholder='', tag='button', input_type='', context='Email Password', **kw)


@pytest.fixture
def setup(client, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    plan = demonstrated_plan(Mapping(**MAPPING), 'Actual Result')
    dataset = storage.put('dataset', {'id': storage.uid(), 'rows': [{'Email': 'private@example.com', 'Password': 'secret123', 'Expected Result': 'Login successful'}]})
    run = storage.put('run', {'id': storage.uid(), 'dataset_id': dataset['id'], 'state': 'running', 'plan': plan.model_dump()})
    page = MagicMock()
    page.is_closed.return_value = False
    page.url = plan.url
    page.evaluate.return_value = [candidate().model_dump()]
    page.locator.return_value.click.side_effect = [BrowserError('missing'), None]
    return plan, dataset, run, page


def approve(monkeypatch, client):
    def ask(run_id, proposal):
        storage.put('recovery', proposal)
        response = client.post(f"/runs/{run_id}/recoveries/{proposal['id']}/approve")
        assert response.status_code == 200
        return response.json()
    monkeypatch.setattr(r, 'ask', ask)
    monkeypatch.setattr(executor, 'start', lambda _: None)


def perform(setup):
    plan, dataset, run, page = setup
    return r.perform(page, run['id'], 0, plan, plan.steps[2], dataset, lambda loc: loc.click())


def test_exact_selector_no_agent(setup, monkeypatch):
    setup[3].locator.return_value.click.side_effect = None
    monkeypatch.setattr(r, 'discover', lambda *a: pytest.fail('Unnecessary recovery'))
    perform(setup)
    assert not r.history(setup[2]['id'])


@pytest.mark.parametrize('name', ['Sign In', 'Login', 'Log in'])
def test_changed_button_or_id_approved_and_remembered(setup, client, monkeypatch, name):
    setup[3].evaluate.return_value = [candidate(name).model_dump()]
    approve(monkeypatch, client)
    perform(setup)
    run_id = setup[2]['id']
    assert r.history(run_id)[0]['state'] == 'acted'
    assert not storage.listing('recovery_memory')
    storage.checkpoint(run_id, 0, 'PASS')
    r.verify_row(run_id, 0)
    assert r.history(run_id)[0]['state'] == 'recovered'
    assert len(storage.listing('recovery_memory')) == 1
    setup[3].locator.return_value.click.side_effect = [BrowserError('missing'), None]
    monkeypatch.setattr(r, 'ask', lambda *a: pytest.fail('Repeated approval'))
    monkeypatch.setattr(r, 'evaluate', lambda *a: pytest.fail('Repeated model call'))
    perform(setup)
    assert r.history(run_id)[0]['method'] == 'Approved memory'


def test_input_label_and_position_changed(setup):
    plan = setup[0]
    original = r.intent(plan, plan.steps[0])
    c = candidate().model_copy(update={'name': 'Email address', 'label': 'Email address', 'placeholder': 'Email', 'role': 'textbox', 'tag': 'input', 'input_type': 'email'})
    ranked = r.rank(original, [c])
    assert ranked[0][0] >= .75
    assert not r.compatible(r.intent(plan, plan.steps[1]), c)
    assert r.compatible(r.intent(plan, plan.steps[2]), candidate().model_copy(update={'tag': 'div'}))


def test_ambiguous_candidates_never_automatically_selected(setup, monkeypatch):
    setup[3].evaluate.return_value = [candidate().model_dump(), candidate().model_copy(update={'id': 1}).model_dump()]
    monkeypatch.setattr(r, 'ask', lambda *a: pytest.fail('Ambiguous fallback'))
    with pytest.raises(BrowserError):
        perform(setup)
    assert r.history(setup[2]['id'])[0]['state'] == 'not_found'


def test_reject_waiting_worker(setup, client):
    run_id = setup[2]['id']
    proposal = {'id': storage.uid(), 'run_id': run_id, 'state': 'pending'}
    caught = []
    def wait():
        try: r.ask(run_id, proposal)
        except r.RecoveryDeclined: caught.append(True)
    worker = threading.Thread(target=wait)
    worker.start()
    for _ in range(100):
        if storage.get('recovery', proposal['id']): break
        time.sleep(.01)
    url = f"/runs/{run_id}/recoveries/{proposal['id']}/reject"
    assert client.post(url).status_code == 200
    worker.join(2)
    assert not worker.is_alive() and caught
    assert client.post(url).status_code == 409


def test_approval_resumes_waiting_worker(setup, client, monkeypatch):
    monkeypatch.setattr(executor, 'start', lambda _: None)
    run_id = setup[2]['id']
    proposal = {'id': storage.uid(), 'run_id': run_id, 'state': 'pending'}
    returned = []
    worker = threading.Thread(target=lambda: returned.append(r.ask(run_id, proposal)))
    worker.start()
    for _ in range(100):
        if storage.get('recovery', proposal['id']): break
        time.sleep(.01)
    assert client.post(f"/runs/{run_id}/recoveries/{proposal['id']}/approve").status_code == 200
    worker.join(2)
    assert not worker.is_alive() and returned[0]['state'] == 'approved'


def test_stale_candidate_requires_new_observation(setup, client, monkeypatch):
    approve(monkeypatch, client)
    setup[3].evaluate.side_effect = [[candidate().model_dump()], []]
    with pytest.raises(BrowserError): perform(setup)
    assert r.history(setup[2]['id'])[0]['state'] == 'failed'
    assert not storage.listing('recovery_memory')


def test_no_candidate_tavily_fallback_and_no_key(setup, monkeypatch):
    setup[3].evaluate.return_value = []
    assert asyncio.run(r.search(r.intent(setup[0], setup[0].steps[2])))[1].startswith('Tavily not configured')
    called = []
    async def search(original):
        called.append(original)
        return [], 'No allowed page found'
    monkeypatch.setattr(r, 'search', search)
    with pytest.raises(BrowserError): perform(setup)
    assert len(called) == 1


@pytest.mark.parametrize('raw', ['not json', '{"recovery_found": true}', json.dumps({'recovery_found': True, 'candidate_id': 77, 'confidence': .99, 'reason': 'invented', 'suggested_action': 'click'}), json.dumps({'recovery_found': True, 'candidate_id': 0, 'confidence': .99, 'reason': 'changed action', 'suggested_action': 'fill'})])
def test_invalid_model_json_or_invented_choice(setup, monkeypatch, raw):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test-key')
    async def post(*a, **kw):
        assert 'secret123' not in json.dumps(kw.get('json'))
        return httpx.Response(200, request=httpx.Request('POST', 'https://openrouter.ai'), json={'choices': [{'message': {'content': raw}}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    assert asyncio.run(r.evaluate(r.intent(setup[0], setup[0].steps[2]), [candidate()], [])) is None


def test_tavily_domain_filter_and_boundary(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-key')
    monkeypatch.setattr(r.config, 'DEVELOPER_URL', 'https://demo.example/developer')
    monkeypatch.setattr(r.config, 'DEVELOPER_RECOVERY_URL', 'https://demo.example/developer/sign-in')
    async def post(*a, **kw):
        assert kw['json']['include_domains'] == ['demo.example']
        return httpx.Response(200, request=httpx.Request('POST', 'https://api.tavily.com/search'), json={'results': [{'url': u} for u in ['https://evil.example/login', 'https://demo.example/datasets', 'https://demo.example/developer/sign-in']]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    urls, _ = asyncio.run(r.search({'url': r.config.DEVELOPER_URL, 'name': 'Login'}))
    assert urls == ['https://demo.example/developer/sign-in']
    for url in ['https://demo.example.evil/developer', 'https://user@demo.example/developer', 'http://demo.example/developer', 'https://demo.example/developer?token=private']:
        assert not r.safe_navigation(url, r.config.DEVELOPER_URL)


def test_privacy_and_selector_validation(setup):
    data = candidate().model_dump()
    data['name'] = 'private@example.com secret123'
    setup[3].evaluate.return_value = [data]
    safe = json.dumps([c.model_dump() for c in r.discover(setup[3], setup[1])])
    assert 'secret123' not in safe and 'private@example.com' not in safe
    with pytest.raises(ValueError): r.Candidate.model_validate({**data, 'selector': 'javascript:alert(1)'})


def test_restart_invalidates_pending_approval(setup):
    storage.put('recovery', {'id': 'pending', 'state': 'pending'})
    storage.init()
    assert storage.get('recovery', 'pending')['state'] == 'interrupted'
    assert storage.get('run', setup[2]['id'])['state'] == 'paused'


def test_ai_selects_only_discovered_candidate(setup, client, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test-key')
    async def post(*a, **kw):
        body = json.dumps(kw['json'])
        assert 'secret123' not in body and 'private@example.com' not in body
        return httpx.Response(200, request=httpx.Request('POST', 'https://openrouter.ai'), json={'choices': [{'message': {'content': json.dumps({'recovery_found': True, 'candidate_id': 0, 'confidence': .94, 'reason': 'Same form and equivalent action', 'suggested_action': 'click'})}}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    approve(monkeypatch, client)
    perform(setup)
    assert r.history(setup[2]['id'])[0]['method'] == 'AI / local semantic search'


def test_provider_outage_uses_local_fallback(setup, client, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test-key')
    async def post(*a, **kw):
        raise httpx.ConnectError('private provider diagnostic')
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    approve(monkeypatch, client)
    perform(setup)
    entries = r.history(setup[2]['id'])
    assert entries[0]['method'] == 'Local semantic search'
    assert 'private provider diagnostic' not in json.dumps(entries)


def test_tavily_outage_and_loopback_skip(setup, monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'synthetic-key')
    calls = []
    async def post(*a, **kw):
        calls.append(True)
        raise httpx.ConnectError('private')
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    assert 'local-only' in asyncio.run(r.search({'url': 'http://127.0.0.1:5173/developer', 'name': 'Login'}))[1]
    assert not calls
    urls, note = asyncio.run(r.search({'url': 'https://demo.example/developer', 'name': 'Login'}))
    assert not urls and 'unavailable' in note and len(calls) == 1


def test_stop_cancels_pending_and_wrong_run_blocked(setup, client):
    run_id = setup[2]['id']
    entry = storage.put('recovery', {'id': storage.uid(), 'run_id': run_id, 'state': 'pending'})
    other = storage.put('run', {**setup[2], 'id': storage.uid()})
    assert client.post(f"/runs/{other['id']}/recoveries/{entry['id']}/approve").status_code == 409
    assert client.post(f'/runs/{run_id}/stop').status_code == 200
    assert storage.get('recovery', entry['id'])['state'] == 'cancelled'
    assert client.post(f"/runs/{run_id}/recoveries/{entry['id']}/approve").status_code == 409


def test_provider_call_inside_running_event_loop():
    async def value(): return 'validated'
    async def caller(): return r.provider_call(value())
    assert asyncio.run(caller()) == 'validated'


def test_approved_navigation_restarts_row_and_repeats_discovery(setup, client, monkeypatch):
    from backend.tests.test_executor import browser_fixture
    page = browser_fixture(monkeypatch)
    page.goto.side_effect = lambda url, **kw: setattr(page, 'url', url)
    page.locator.return_value.click.side_effect = [BrowserError('old page'), BrowserError('old selector'), None]
    page.locator.return_value.inner_text.return_value = 'Login successful'
    page.evaluate.side_effect = [[], [candidate().model_dump()], [candidate().model_dump()]]
    async def search(original): return [r.config.DEVELOPER_RECOVERY_URL], 'Domain search'
    monkeypatch.setattr(r, 'search', search)
    approve(monkeypatch, client)
    run = setup[2]
    storage.put('run', {**run, 'retries': 0})
    executor.execute(run['id'])
    assert storage.get('run', run['id'])['state'] == 'completed'
    assert storage.results(run['id'])[0]['status'] == 'PASS'
    entries = r.history(run['id'])
    assert len(entries) == 2 and all(e['state'] == 'recovered' for e in entries)
    assert page.goto.call_args_list[-1].args[0] == r.config.DEVELOPER_RECOVERY_URL


def test_rejected_recovery_checkpoints_error_and_never_remembers(setup, monkeypatch):
    from backend.tests.test_executor import browser_fixture
    page = browser_fixture(monkeypatch)
    page.url = setup[0].url
    page.locator.return_value.click.side_effect = BrowserError('missing')
    page.evaluate.return_value = [candidate().model_dump()]
    def reject(*args): raise r.RecoveryDeclined()
    monkeypatch.setattr(r, 'ask', reject)
    storage.put('run', {**setup[2], 'retries': 0})
    executor.execute(setup[2]['id'])
    assert storage.results(setup[2]['id'])[0]['status'] == 'ERROR'
    assert not storage.listing('recovery_memory')


def test_unverified_action_is_not_remembered(setup, client, monkeypatch):
    approve(monkeypatch, client)
    perform(setup)
    r.finish_row(setup[2]['id'], 0)
    assert r.history(setup[2]['id'])[0]['state'] == 'unverified'
    assert not storage.listing('recovery_memory')
