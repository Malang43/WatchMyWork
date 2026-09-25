"""Focused recorder regression: existing result node, fast/delayed text, live 30/70.

Start the local backend and mock site. No AI inference or execution is requested.
"""
import tempfile
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
client = httpx.Client(base_url='http://127.0.0.1:8000', headers={'X-WatchMyWork': 'local-demo'})
assert client.get('/teach/current').json() is None, 'Finish the current recording before running this test.'

with sync_playwright() as pw:
    extension = str(ROOT / 'extension')
    context = pw.chromium.launch_persistent_context(tempfile.mkdtemp(prefix='wmw-recording-'), channel='chromium', headless=True, args=[f'--disable-extensions-except={extension}', f'--load-extension={extension}'])
    try:
        for mode in ['delayed', 'immediate', 'live']:
            dataset = client.post('/datasets', files={'file': ('weather-recording.csv', 'Latitude,Longitude,Temperature\n30,70,\n'.encode(), 'text/csv')}).json()
            response = client.post('/demos', json={'dataset_id': dataset['id'], 'row_index': 0, 'input_columns': ['Latitude', 'Longitude'], 'destination_column': 'Temperature'})
            assert response.status_code == 200
            demo_id = response.json()['id']
            page = context.new_page()
            if mode != 'live':
                # No form and no weather-result/data-state: detection depends only
                # on the stable button/result IDs and changed text, as required.
                delay = 'setTimeout(update, 80)' if mode == 'delayed' else 'update()'
                html = '''<input id="latitude-input"><input id="longitude-input">
                <button id="check-weather-button">Check Weather</button>
                <output id="temperature-result">99 °C</output>
                <script>window.originalResult = document.querySelector('#temperature-result');
                document.querySelector('button').onclick = () => {
                  const update = () => { originalResult.firstChild.data = '0 °C'; };
                  REPLACE_DELAY;
                };</script>'''.replace('REPLACE_DELAY', delay)
                page.route('http://127.0.0.1:5173/', lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=html))
            page.goto('http://127.0.0.1:5173/')
            overlay = page.locator('#watchmywork-recorder')
            expect(overlay).to_have_attribute('data-recording', demo_id, timeout=15000)
            page.locator('#latitude-input').fill('30')
            page.locator('#longitude-input').fill('70')
            page.locator('#check-weather-button').click()
            try:
                expect(overlay).to_have_attribute('data-state', 'saved', timeout=20000)
            except AssertionError:
                print('Recording diagnostic:', mode, page.locator('body').inner_text(), flush=True)
                print('Events:', client.get('/demos', params={'dataset_id': dataset['id']}).json()[0]['events'], flush=True)
                raise
            temperature = page.locator('#temperature-result').inner_text().strip()
            expect(overlay).to_have_text(f'✓ Demonstration saved · Temperature captured: {temperature}')
            if mode != 'live':
                assert temperature == '0 °C'
                assert page.evaluate("window.originalResult === document.querySelector('#temperature-result')")
            saved = client.get('/demos', params={'dataset_id': dataset['id']}).json()[0]
            assert saved['state'] == 'complete' and saved['result'] == temperature
            assert [(e['target'], e['value']) for e in saved['events'] if e['action'] == 'fill'] == [('#latitude-input', '30'), ('#longitude-input', '70')]
            assert len([e for e in saved['events'] if e['action'] == 'click']) == 1
            assert len([e for e in saved['events'] if e['action'] == 'wait']) == 1
            assert len([e for e in saved['events'] if e['action'] == 'extract']) == 1
            page.evaluate("document.querySelector('#temperature-result').textContent = '17 °C'")
            page.wait_for_timeout(1200)
            again = client.get('/demos', params={'dataset_id': dataset['id']}).json()[0]
            assert again['events'] == saved['events'] and again['result'] == temperature
            expect(overlay).to_have_text(f'✓ Demonstration saved · Temperature captured: {temperature}')
            assert client.get('/teach/current').json() is None
            print(f'PASS {mode}: 30/70 -> {temperature}; automatic completion, confirmation and no duplicate extraction', flush=True)
            page.close()
    finally:
        context.close()
        current = client.get('/teach/current').json()
        if current and current['id'] == demo_id:
            client.post(f'/demos/{demo_id}/stop')
