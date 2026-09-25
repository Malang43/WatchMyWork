"""Verify production recording and analysis using synthetic data.

Does not approve, execute workflows, or remove persisted data.
"""
import argparse
import re
import tempfile
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

ORIGIN = 'https://watchmywork-production.up.railway.app'
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stop-active', action='store_true', help='Stop the existing recording without deleting its data.')
args = parser.parse_args()

with httpx.Client(base_url=ORIGIN, timeout=30) as client:
    response = client.get('/teach/current')
    response.raise_for_status()
    active = response.json()
    if active is None:
        print('No active production recording; existing saved data untouched.', flush=True)
    if active and args.stop_active:
        stopped = client.post('/demos/' + active['id'] + '/stop', headers={'X-WatchMyWork': 'local-demo'})
        stopped.raise_for_status()
        saved = stopped.json()
        persisted = client.get('/demos', params={'dataset_id': saved['dataset_id']})
        persisted.raise_for_status()
        assert next(d for d in persisted.json() if d['id'] == saved['id']) == saved
        print(f"Existing recording preserved: demonstration_id={saved['id']} state={saved['state']} event_count={len(saved['events'])}", flush=True)
        active = client.get('/teach/current').json()
    assert active is None, 'An existing recording is active; finish it before running this test.'

with sync_playwright() as pw:
    extension = str(ROOT / 'extension')
    with tempfile.TemporaryDirectory(prefix='wmw-production-teach-') as profile:
        context = pw.chromium.launch_persistent_context(
            profile, channel='chromium', headless=True,
            args=[f'--disable-extensions-except={extension}', f'--load-extension={extension}'],
        )
        try:
            requests = []
            context.on('request', lambda request: requests.append(request.url))
            page = context.new_page()
            page.goto(ORIGIN)
            page.get_by_role('button', name='New Workflow', exact=True).last.click()
            # New Workflow checks /teach/current before mounting the fresh wizard.
            # set_input_files can target a hidden input, so wait for navigation.
            expect(page.get_by_label('Upload spreadsheet')).to_be_visible()
            with page.expect_response(lambda response: response.url == ORIGIN + '/datasets' and response.request.method == 'POST') as upload:
                page.get_by_label('Upload spreadsheet').set_input_files({
                    'name': 'production-teach-regression.csv', 'mimeType': 'text/csv',
                    'buffer': b'Email,Password,Expected Result,Actual Result,Status\ndev@example.com,test123,Login successful,,\n',
                })
            assert upload.value.status == 200, f'Upload returned HTTP {upload.value.status}'
            dataset = upload.value.json()
            assert 'id' in dataset and 'columns' in dataset, 'Upload did not return dataset metadata'
            print('Synthetic upload=200', flush=True)
            page.get_by_label('Input 1', exact=True).select_option('Email')
            page.get_by_label('Input 2 (optional)', exact=True).select_option('Password')
            page.get_by_label('Destination / output column', exact=True).select_option('Actual Result')
            page.get_by_label('Expected output', exact=True).select_option('Expected Result')
            page.get_by_label('Test status', exact=True).select_option('Status')
            page.get_by_role('button', name='Continue to Teach').click()
            analyze = page.get_by_role('button', name='Analyze Workflow')
            expect(analyze).to_be_disabled()
            page.get_by_role('button', name='Start Recording').click()
            portal = context.new_page()
            portal.goto(ORIGIN + '/developer')
            overlay = portal.locator('#watchmywork-recorder')
            expect(overlay).to_have_attribute('data-recording', re.compile('[a-f0-9]{32}'), timeout=30000)
            demo_id = overlay.get_attribute('data-recording')
            worker = context.service_workers[0]
            statuses = []
            context.on('response', lambda response: statuses.append((response.url, response.status)))
            portal.locator('#email-input').fill('dev@example.com')
            portal.locator('#password-input').fill('test123')
            portal.locator('#login-button').click()
            expect(overlay).to_have_text('✓ Test demonstration captured', timeout=30000)
            expect(analyze).to_be_enabled(timeout=15000)
            # Fetch persisted state from the extension's own origin as well.
            result = worker.evaluate('''async ({origin, id}) => {
                const response = await fetch(origin + '/demos/' + id + '/stop', {
                    method: 'POST', headers: {'X-WatchMyWork': 'local-demo'}
                });
                const data = await response.json();
                return {status: response.status, state: data.state};
            }''', {'origin': ORIGIN, 'id': demo_id})
            assert result == {'status': 200, 'state': 'complete'}, result
            assert any(url.endswith('/events') and status == 200 for url, status in statuses)
            assert not any(re.match(r'http://(?:127\.0\.0\.1|localhost):(?:8000|8001|5173)', url) for url in requests)
            page.reload()
            page.get_by_role('button', name='New Workflow', exact=True).first.click()
            expect(page.get_by_role('button', name='Analyze Workflow')).to_be_enabled(timeout=15000)
            print(f'PASS demonstration_id={demo_id} events=200 save=200 state=complete captured_message=visible Analyze=enabled restored=enabled localhost_requests=0', flush=True)
            with page.expect_response(lambda response: response.url == ORIGIN + '/workflows/infer' and response.request.method == 'POST', timeout=400000) as inference:
                page.get_by_role('button', name='Analyze Workflow').click()
            response = inference.value
            assert response.status == 200, f'Analyze returned HTTP {response.status}'
            workflow = response.json()
            assert demo_id in workflow['demo_ids']
            assert workflow['confirmed'] is False
            expect(page.get_by_role('button', name='Confirm Workflow')).to_be_visible(timeout=15000)
            print(f"PASS Analyze POST /workflows/infer=200 workflow_id={workflow['id']} source={workflow['source']} review=visible confirmed=false", flush=True)
        finally:
            context.close()
