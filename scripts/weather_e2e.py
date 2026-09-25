"""Live weather: Excel, real extension, Nemotron, confirmation, execution, export.

Start backend, frontend and mock-site first. Uses synthetic coordinates only.
"""
import io
import argparse
import json
import re
import tempfile
import time
from pathlib import Path
import httpx
from openpyxl import Workbook, load_workbook
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'test-results'
ARTIFACTS.mkdir(exist_ok=True)
ROWS = [('33.6844', '73.0479'), ('24.8607', '67.0011'), ('51.5074', '-0.1278')]
OUTPUT = 'Current Temperature (°C)'
parser = argparse.ArgumentParser()
parser.add_argument('--manual', action='store_true', help='Test the existing explicit inference-outage fallback')
args = parser.parse_args()
book = Workbook()
book.active.append(['Latitude', 'Longitude', OUTPUT])
for lat, lon in ROWS:
    book.active.append([lat, lon, ''])
book.save(ARTIFACTS / 'weather-input.xlsx')
client = httpx.Client(base_url='http://127.0.0.1:8000', headers={'X-WatchMyWork': 'local-demo'}, timeout=135)

with sync_playwright() as pw:
    extension = str(ROOT / 'extension')
    context = pw.chromium.launch_persistent_context(tempfile.mkdtemp(prefix='wmw-weather-'), channel='chromium', headless=True, args=[f'--disable-extensions-except={extension}', f'--load-extension={extension}'], viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
    app = context.new_page()
    errors = []
    app.on('pageerror', lambda error: errors.append(str(error)))
    try:
        app.goto('http://127.0.0.1:5174/')
        app.get_by_role('button', name='New Workflow', exact=True).last.click()
        expect(app.get_by_role('heading', name='Show us how you work.', exact=True)).to_be_visible()
        with app.expect_response(lambda r: r.url.endswith('/datasets') and r.request.method == 'POST') as uploaded:
            app.get_by_label('Upload spreadsheet').set_input_files(str(ARTIFACTS / 'weather-input.xlsx'))
        dataset = uploaded.value.json()
        app.get_by_label('Input 1', exact=True).select_option('Latitude')
        app.get_by_label('Input 2 (optional)', exact=True).select_option('Longitude')
        app.get_by_label('Destination / output column', exact=True).select_option(OUTPUT)
        app.get_by_role('button', name='Continue to Teach').click()
        app.get_by_role('button', name='Start Recording').click()
        mock = context.new_page()
        mock.on('pageerror', lambda error: errors.append(str(error)))
        mock.goto('http://127.0.0.1:5173/')
        overlay = mock.locator('#watchmywork-recorder')
        expect(overlay).to_have_attribute('data-recording', re.compile(r'^[a-f0-9]{32}$'), timeout=15000)
        expect(overlay).to_contain_text('Enter Latitude and Longitude, click Check Weather')
        mock.locator('#latitude-input').fill(ROWS[0][0])
        mock.locator('#longitude-input').fill(ROWS[0][1])
        mock.locator('#check-weather-button').click()
        expect(mock.locator('#temperature-result')).to_be_visible(timeout=15000)
        first_temperature = mock.locator('#temperature-result').inner_text()
        expect(overlay).to_have_attribute('data-state', 'saved', timeout=15000)
        expect(overlay).to_contain_text('Demonstration saved')
        demos = client.get('/demos', params={'dataset_id': dataset['id']}).json()
        assert demos[0]['state'] == 'complete'
        meaningful = [e for e in demos[0]['events'] if e['action'] not in ('navigate', 'focus')]
        assert [e['action'] for e in meaningful] == ['fill', 'fill', 'click', 'wait', 'extract']
        assert [e['target'] for e in meaningful[:2]] == ['#latitude-input', '#longitude-input']
        print('PASS: Excel selection, both weather inputs, real API result and extension automatic save', flush=True)
        app.bring_to_front()
        if args.manual:
            app.route('**/workflows/infer', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'Simulated outage for explicit manual-path verification.'})))
            app.get_by_role('button', name='Analyze Workflow').click()
            expect(app.get_by_role('alert')).to_contain_text('Simulated outage')
            with app.expect_response(lambda r: r.url.endswith('/workflows/manual')) as inferred:
                app.get_by_role('button', name='Review demonstrated steps manually').click()
        else:
            for attempt in range(3):
                with app.expect_response(lambda r: r.url.endswith('/workflows/infer'), timeout=135000) as inferred:
                    app.get_by_role('button', name='Analyze Workflow' if attempt == 0 else 'Retry', exact=False).click()
                if inferred.value.status == 200:
                    break
                print(f'Inference attempt {attempt + 1}: {inferred.value.json().get("detail")}', flush=True)
        assert inferred.value.status == 200, 'Live Nemotron inference unavailable'
        workflow = inferred.value.json()
        assert workflow['source'] == ('manual' if args.manual else 'nemotron')
        assert workflow['plan']['input_columns'] == ['Latitude', 'Longitude']
        assert [s['value'] for s in workflow['plan']['steps'][:2]] == ['{{row.Latitude}}', '{{row.Longitude}}']
        calls = client.get('/metrics').json()['total_ai_calls']
        payload = {'workflow_id': workflow['id'], 'dataset_id': dataset['id']}
        assert client.post('/runs', json=payload).status_code == 409
        app.get_by_role('button', name='Confirm Workflow', exact=True).click()
        with app.expect_response(lambda r: r.url.endswith('/runs') and r.request.method == 'POST') as started:
            app.get_by_role('button', name='Run Workflow').click()
        assert started.value.status == 200
        run_id = started.value.json()['id']
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            run = client.get(f'/runs/{run_id}').json()
            if run['state'] == 'completed': break
            assert run['state'] == 'running', run.get('error')
            time.sleep(.3)
        assert run['state'] == 'completed' and run['successful'] == 3, run
        expect(app.get_by_role('heading', name='Workflow Complete', exact=True)).to_be_visible(timeout=10000)
        with app.expect_download() as downloaded:
            app.get_by_role('link', name='Download Updated Excel').click()
        downloaded.value.save_as(ARTIFACTS / 'weather-output.xlsx')
        output = list(load_workbook(ARTIFACTS / 'weather-output.xlsx').active.values)
        assert output[0] == ('Latitude', 'Longitude', OUTPUT)
        assert output[1][2] == first_temperature
        for row, coords in zip(output[1:], ROWS):
            assert row[:2] == coords
            assert re.fullmatch(r'[+-]?\d+(?:\.\d+)? °C', row[2])
            response = httpx.get('https://api.open-meteo.com/v1/forecast', params={'latitude': coords[0], 'longitude': coords[1], 'current': 'temperature_2m'}, timeout=20)
            response.raise_for_status()
            assert float(row[2].split()[0]) == response.json()['current']['temperature_2m']
        assert client.get('/metrics').json()['total_ai_calls'] == calls
        assert not errors, errors
        app.screenshot(path=str(ARTIFACTS / 'weather-complete.png'), full_page=True)
        (ARTIFACTS / ('weather-manual-e2e.json' if args.manual else 'weather-e2e.json')).write_text(json.dumps({'workflow_id': workflow['id'], 'run_id': run_id, 'rows': output[1:], 'successful': run['successful'], 'inference': workflow['source'], 'per_row_ai_calls': 0}, indent=2), encoding='utf-8')
        print(f'PASS: {workflow["source"]} two-variable workflow, approval, 3 real coordinate rows, Excel export, zero per-row AI calls', flush=True)
    finally:
        context.close()
