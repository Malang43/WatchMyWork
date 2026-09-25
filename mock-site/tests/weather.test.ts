import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchWeather, parseCoordinates, parseTemperature, WeatherError } from '../src/weather.ts';

const body = (temperature: unknown = 26.4, unit = '°C') => ({ current: { temperature_2m: temperature }, current_units: { temperature_2m: unit } });
const reply = (value: unknown): typeof fetch => async () => Response.json(value);

test('parses decimal coordinates, whitespace, negative numbers, zero and boundaries', () => {
  assert.deepEqual(parseCoordinates(' 33.6844 ', '73.0479'), { latitude: 33.6844, longitude: 73.0479 });
  assert.deepEqual(parseCoordinates('-90', '180'), { latitude: -90, longitude: 180 });
  assert.deepEqual(parseCoordinates('90', '-180'), { latitude: 90, longitude: -180 });
  assert.deepEqual(parseCoordinates('0', '0'), { latitude: 0, longitude: 0 });
  assert.deepEqual(parseCoordinates('+.5', '-.25'), { latitude: .5, longitude: -.25 });
});

for (const [lat, lon, field] of [['', '1', 'latitude'], [' ', '1', 'latitude'], ['1', '', 'longitude'], ['1', ' ', 'longitude'], ['90.01', '0', 'latitude'], ['-90.01', '0', 'latitude'], ['0', '180.01', 'longitude'], ['0', '-180.01', 'longitude'], ['abc', '0', 'latitude'], ['33,68', '0', 'latitude'], ['0', 'Infinity', 'longitude'], ['0x10', '0', 'latitude'], ['1e2', '0', 'latitude']]) {
  test(`rejects invalid coordinates ${JSON.stringify([lat, lon])}`, () => {
    assert.throws(() => parseCoordinates(lat, lon), (error: unknown) => error instanceof WeatherError && error.field === field);
  });
}

test('reads the actual numeric API temperature, including zero and negative values', () => {
  for (const value of [26.4, 0, -12.7]) assert.equal(parseTemperature(body(value)), value);
});

test('rejects missing, null, nonnumeric, nonfinite, wrong-unit and error responses', () => {
  for (const value of [null, [], {}, { current: {} }, body(null), body('26.4'), body(Infinity), body(NaN), body(80, '°F'), { ...body(), error: true }]) {
    assert.throws(() => parseTemperature(value), WeatherError);
  }
});

test('requests only the specified endpoint and returns its temperature with the submitted coordinates', async () => {
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = new URL(String(input));
    assert.equal(url.origin + url.pathname, 'https://api.open-meteo.com/v1/forecast');
    assert.deepEqual(Object.fromEntries(url.searchParams), { latitude: '33.6844', longitude: '73.0479', current: 'temperature_2m' });
    assert.equal(init?.credentials, 'omit');
    assert.equal(new Headers(init?.headers).has('Authorization'), false);
    return Response.json(body(27.8));
  };
  assert.deepEqual(await fetchWeather('33.6844', '73.0479', { fetchImpl }), { latitude: 33.6844, longitude: 73.0479, temperature: 27.8 });
});

test('invalid input never makes a network request', async () => {
  let calls = 0;
  const fetchImpl: typeof fetch = async () => { calls++; return Response.json(body()); };
  await assert.rejects(fetchWeather('', '73', { fetchImpl }), /Enter a latitude/);
  assert.equal(calls, 0);
});

test('network failures become friendly errors without provider details', async () => {
  const fetchImpl: typeof fetch = async () => { throw new TypeError('internal network detail'); };
  await assert.rejects(fetchWeather('1', '2', { fetchImpl }), /Check your internet connection/);
});

test('HTTP errors and rate limits have retry guidance', async () => {
  for (const code of [400, 429, 500, 503]) {
    const fetchImpl: typeof fetch = async () => new Response('', { status: code });
    await assert.rejects(fetchWeather('1', '2', { fetchImpl }), code === 429 ? /service is busy/ : /temporarily unavailable/);
  }
});

test('invalid JSON and malformed successful responses are rejected', async () => {
  await assert.rejects(fetchWeather('1', '2', { fetchImpl: async () => new Response('not JSON') }), /unreadable response/);
  await assert.rejects(fetchWeather('1', '2', { fetchImpl: reply(body(null)) }), /valid temperature/);
});

const neverReply: typeof fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
  if (init?.signal?.aborted) reject(new DOMException('Aborted', 'AbortError'));
  else init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
});

test('timeout aborts the request and gives a retry message', async () => {
  await assert.rejects(fetchWeather('1', '2', { fetchImpl: neverReply, timeoutMs: 10 }), /request timed out/);
});

test('changing coordinates can cancel an in-flight request without a network error', async () => {
  const controller = new AbortController();
  const pending = fetchWeather('1', '2', { fetchImpl: neverReply, signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, (error: Error) => error.name === 'AbortError');
});
