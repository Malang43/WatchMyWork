"""Local browser integration checks independent of free-model availability."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

artifacts = Path(__file__).resolve().parents[1] / 'test-results'
artifacts.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 960})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:5173/')
    for value, expected in [('PK100001', 'Delivered'), ('PK100002', 'Pending'), ('PK100003', 'In Transit'), ('PK100004', 'Returned'), ('PK100005', 'Not Found'), ('  pk100001  ', 'Delivered'), ('UNKNOWN', 'Not Found')]:
        page.get_by_label('Tracking ID', exact=True).fill(value)
        page.get_by_label('Tracking ID', exact=True).press('Enter')
        expect(page.locator('#tracking-result .status')).to_have_text(expected)
    page.get_by_label('Tracking ID', exact=True).fill('')
    expect(page.locator('#tracking-result .status')).to_have_count(0)
    page.get_by_role('button', name='Check Status').click()
    expect(page.get_by_role('alert')).to_contain_text('Enter a tracking ID')
    page.goto('http://127.0.0.1:5174/')
    expect(page.get_by_role('heading', name='Less repetition. More possibility.')).to_be_visible()
    page.screenshot(path=str(artifacts / 'dashboard-current.png'), full_page=True)
    for navigation, heading in [('Saved Workflows', 'Saved workflows'), ('Runs', 'Runs'), ('Settings', 'Settings'), ('Research Metrics', 'Research metrics')]:
        page.get_by_role('button', name=navigation, exact=True).click()
        expect(page.get_by_role('heading', name=heading, exact=True)).to_be_visible()
    page.get_by_role('button', name='Dashboard', exact=True).click()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(artifacts / 'mobile-current.png'), full_page=True)
    assert errors == [], errors
    browser.close()
print('PASS: all five mock records, unknown/blank input, Enter submission, cleared stale results, main navigation, and mobile layout. No browser runtime errors.')
