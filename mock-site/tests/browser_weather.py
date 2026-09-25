"""Run from the project root with the existing .venv; pass --live to check Open-Meteo too."""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true')
args = parser.parse_args()
API = 'https://api.open-meteo.com/v1/forecast*'
artifacts = Path(__file__).resolve().parents[2] / 'test-results'
artifacts.mkdir(exist_ok=True)

def payload(value):
    return {'current': {'temperature_2m': value}, 'current_units': {'temperature_2m': '\u00b0C'}}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = context.new_page()
    errors = []
    requests = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request) if 'api.open-meteo.com' in request.url else None)
    page.goto('http://127.0.0.1:5173/')
    lat = page.get_by_role('textbox', name='Latitude', exact=True)
    lon = page.get_by_role('textbox', name='Longitude', exact=True)
    button = page.get_by_role('button', name='Check Weather', exact=True)
    result = page.locator('#temperature-result')
    expect(lat).to_have_attribute('id', 'latitude-input')
    expect(lon).to_have_attribute('name', 'longitude')
    expect(button).to_have_attribute('id', 'check-weather-button')
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('Enter a latitude')
    expect(lat).to_be_focused()
    lat.fill('33.6844')
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('Enter a longitude')
    lon.fill('181')
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('between -180 and 180')
    lat.fill('not-a-number')
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('valid latitude')
    assert not requests, 'Invalid inputs must never call the API'

    page.route(API, lambda route: route.fulfill(json=payload(24.7)))
    lat.fill('33.6844'); lon.fill('73.0479')
    lon.press('Enter')
    expect(result).to_have_text('24.7 \u00b0C')
    expect(result).to_have_attribute('data-temperature', '24.7')
    assert parse_qs(urlparse(requests[-1].url).query) == {'latitude': ['33.6844'], 'longitude': ['73.0479'], 'current': ['temperature_2m']}
    assert 'authorization' not in requests[-1].headers
    lat.fill('0')
    expect(result).to_have_text('')
    page.unroute(API)

    for value in [0, -5.3]:
        page.route(API, lambda route, request, value=value: route.fulfill(json=payload(value)))
        button.click()
        expect(result).to_have_text(f'{value} \u00b0C')
        page.unroute(API)

    for response in [None, {}, payload(None), payload('26.1'), {'current': {'temperature_2m': 55}, 'current_units': {'temperature_2m': 'F'}}]:
        page.route(API, lambda route, request, value=response: route.fulfill(content_type='application/json', body=json.dumps(value)))
        button.click()
        expect(page.get_by_role('alert')).to_contain_text('response' if response is None or response == {} else 'valid temperature')
        expect(result).to_have_text('')
        expect(button).to_be_enabled()
        page.unroute(API)

    page.route(API, lambda route: route.fulfill(content_type='application/json', body='not JSON'))
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('unreadable response')
    page.unroute(API)
    page.route(API, lambda route: route.abort('internetdisconnected'))
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('internet connection')
    page.unroute(API)
    page.route(API, lambda route: route.fulfill(status=503, body='Unavailable'))
    button.click()
    expect(page.get_by_role('alert')).to_contain_text('temporarily unavailable')
    page.unroute(API)

    # A real ten-second deadline, accelerated with the browser's test clock.
    page.clock.install()
    page.evaluate('''() => {
      window.originalWeatherFetch = window.fetch;
      window.fetch = (_url, options) => new Promise((_resolve, reject) => {
        window.pendingWeatherSignal = options.signal;
        options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      });
    }''')
    button.click()
    expect(button).to_be_disabled()
    expect(page.locator('#weather-result')).to_have_attribute('data-state', 'loading')
    page.clock.fast_forward(11000)
    expect(page.get_by_role('alert')).to_contain_text('request timed out')
    expect(button).to_be_enabled()

    # Editing during a request cancels it and prevents stale coordinates/results.
    button.click()
    expect(button).to_be_disabled()
    lat.fill('1')
    assert page.evaluate('window.pendingWeatherSignal.aborted')
    expect(button).to_be_enabled()
    expect(result).to_have_text('')
    page.evaluate('window.fetch = window.originalWeatherFetch')
    page.route(API, lambda route: route.fulfill(json=payload(12.8)))
    button.click()
    expect(result).to_have_text('12.8 \u00b0C')
    page.screenshot(path=str(artifacts / 'weather-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 375, 'height': 812})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(artifacts / 'weather-mobile.png'), full_page=True)
    assert errors == [], errors
    page.unroute_all(behavior='ignoreErrors')
    context.close()
    print('PASS: weather browser validation, exact endpoint, Enter submission, Celsius results, error recovery, timeout, stale-request cancellation, mobile layout, and no runtime errors.', flush=True)

    if args.live:
        context = browser.new_context()
        page = context.new_page()
        page.goto('http://127.0.0.1:5173/')
        page.get_by_label('Latitude', exact=True).fill('33.6844')
        page.get_by_label('Longitude', exact=True).fill('73.0479')
        with page.expect_response(lambda response: response.url.startswith('https://api.open-meteo.com/v1/forecast?'), timeout=15000) as response:
            page.get_by_role('button', name='Check Weather', exact=True).click()
        assert response.value.ok, f'Live provider HTTP {response.value.status}'
        temperature = response.value.json()['current']['temperature_2m']
        assert isinstance(temperature, (int, float)) and math.isfinite(temperature)
        expected = str(int(temperature)) if temperature == int(temperature) else str(temperature)
        expect(page.locator('#temperature-result')).to_have_text(expected + ' \u00b0C')
        page.screenshot(path=str(artifacts / 'weather-live.png'), full_page=True)
        print(f'PASS: live Open-Meteo response matched the UI for 33.6844, 73.0479: {temperature} C.', flush=True)
        context.close()
    browser.close()
