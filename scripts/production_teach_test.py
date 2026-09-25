"""Verify only production recording and Analyze readiness using synthetic data.

Does not analyze, approve, execute workflows, or remove persisted data.
"""
import re
import tempfile
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

ORIGIN = 'https://watchmywork-production.up.railway.app'
ROOT = Path(__file__).resolve().parents[1]

with httpx.Client(base_url=ORIGIN, timeout=30) as client:
    response = client.get('/teach/current')
    response.raise_for_status()
    assert response.json() is None, 'An existing recording is active; finish it before running this test.'

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
            page.get_by_label('Upload spreadsheet').set_input_files({
                'name': 'production-teach-regression.csv', 'mimeType': 'text/csv',
                'buffer': b'Email,Password,Expected Result,Actual Result,Status\ndev@example.com,test123,Login successful,,\n',
            })
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
            expect(page.get_by_role('button', name='Analyze Workflow')).to_be_enabled(timeout=15000)
            print(f'PASS demonstration_id={demo_id} events=200 save=200 state=complete Analyze=enabled restored=enabled localhost_requests=0')
        finally:
            context.close()
