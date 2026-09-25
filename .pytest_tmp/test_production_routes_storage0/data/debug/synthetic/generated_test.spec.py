# Generated from the confirmed WatchMyWork workflow.
# Run: .venv\Scripts\python.exe generated_test.spec.py
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

cases = json.loads(Path(__file__).with_name('test_cases.json').read_text(encoding='utf-8'))
failed = 0
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    try:
        for index, row in enumerate(cases, 1):
            page = browser.new_page()
            try:
                page.goto('https://deployment.example/developer')
                page.locator('#email-input').fill(row['Email'])
                page.locator('#password-input').fill(row['Password'])
                page.locator('#login-button').click()
                result = page.locator('#login-result')
                result.wait_for(state='visible')
                actual = result.inner_text()
                assert actual.strip().casefold() == row['Expected'].strip().casefold(), "Expected and actual results differ"
                print(f'Test {index}: PASS')
            except Exception as exc:
                failed += 1
                print(f'Test {index}: FAIL/ERROR ({type(exc).__name__})')
            finally:
                page.close()
    finally:
        browser.close()
raise SystemExit(1 if failed else 0)
