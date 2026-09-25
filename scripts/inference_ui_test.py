"""Browser regression for inference progress and fallback review (mock API only)."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.schema import demonstrated_plan

async def main():
    dataset = {'id': 'inference-ui-test', 'filename': 'weather.csv', 'columns': ['Latitude', 'Longitude', 'Temperature'], 'record_count': 1, 'preview': [{'Latitude': '30', 'Longitude': '70', 'Temperature': ''}]}
    demo = {'id': 'demo-test', 'state': 'complete', 'row_index': 0, 'input_column': 'Latitude', 'input_columns': ['Latitude', 'Longitude'], 'destination_column': 'Temperature', 'events': [], 'result': '20 °C'}
    workflow = {'id': 'workflow-test', 'plan': demonstrated_plan(['Latitude', 'Longitude'], 'Temperature').model_dump(), 'source': 'semantic_fallback', 'confirmed': False, 'saved': False, 'created_at': '2026-01-01T00:00:00Z'}
    release = asyncio.Event()
    attempt = 1
    async def route_api(route):
        path = route.request.url.split(':8000')[1]
        if path == '/workflows/infer':
            await release.wait()
            data = workflow
        elif path.endswith('/status'): data = {'attempt': attempt, 'state': 'analyzing'}
        elif path == '/health': data = {'ok': True, 'api_key_configured': True}
        elif path == '/dashboard': data = {'workflows_created': 0, 'records_processed': 0, 'successful_automations': 0, 'manual_review_items': 0, 'recent_workflows': [], 'recent_runs': []}
        elif path == '/teach/current': data = None
        elif path.startswith('/demos'): data = [demo]
        elif '/rows/' in path: data = dataset['preview'][0]
        else: data = dataset
        await route.fulfill(content_type='application/json', body=json.dumps(data))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route('http://127.0.0.1:8000/**', route_api)
        await page.add_init_script("sessionStorage.setItem('watchmywork-wizard', JSON.stringify({dataset_id:'inference-ui-test',input:'Latitude',input2:'Longitude',output:'Temperature',step:2}));")
        await page.goto('http://127.0.0.1:5174/')
        await page.get_by_role('button', name='New Workflow', exact=True).first.click()
        await page.get_by_role('button', name='Analyze Workflow').click()
        await expect(page.locator('.busy-banner')).to_contain_text('Analyzing demonstration with Nemotron...')
        attempt = 2
        await expect(page.locator('.busy-banner')).to_contain_text('Nemotron is taking longer than usual — retrying (2/3)...')
        assert await page.get_by_role('alert').count() == 0
        release.set()
        await expect(page.get_by_text('Nemotron temporarily unavailable. A workflow was generated from your recorded actions. Please review it before confirming.', exact=True)).to_be_visible()
        await expect(page.get_by_role('button', name='Confirm Workflow', exact=True)).to_be_visible()
        assert await page.get_by_role('button', name='Run Workflow').count() == 0
        await browser.close()
    print('PASS: initial status, server-reported retry progress, fallback notice, and mandatory confirmation')

asyncio.run(main())
