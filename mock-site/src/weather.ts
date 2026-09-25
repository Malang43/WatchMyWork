export const WEATHER_ENDPOINT = 'https://api.open-meteo.com/v1/forecast';
export const REQUEST_TIMEOUT_MS = 10000;
export type CoordinateField = 'latitude' | 'longitude';
export interface Coordinates { latitude: number; longitude: number }
export interface WeatherResult extends Coordinates { temperature: number }

export class WeatherError extends Error {
  field?: CoordinateField;
  constructor(message: string, field?: CoordinateField) {
    super(message);
    this.name = 'WeatherError';
    this.field = field;
  }
}

export function parseCoordinates(latitude: string, longitude: string): Coordinates {
  const values = { latitude, longitude };
  const result = {} as Coordinates;
  for (const field of ['latitude', 'longitude'] as const) {
    const value = values[field].trim();
    const limit = field === 'latitude' ? 90 : 180;
    if (!value) throw new WeatherError(`Enter a ${field} to check the weather.`, field);
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) || !Number.isFinite(Number(value))) throw new WeatherError(`Enter a valid ${field} in decimal degrees.`, field);
    if (Number(value) < -limit || Number(value) > limit) throw new WeatherError(`${field === 'latitude' ? 'Latitude' : 'Longitude'} must be between -${limit} and ${limit}.`, field);
    result[field] = Number(value);
  }
  return result;
}

export function parseTemperature(body: unknown): number {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) throw new WeatherError('The weather service returned an unexpected response. Please try again.');
  const data = body as Record<string, unknown>;
  const current = data.current;
  const units = data.current_units;
  if (data.error || typeof current !== 'object' || current === null || typeof units !== 'object' || units === null) throw new WeatherError('The weather service returned an unexpected response. Please try again.');
  const temperature = (current as Record<string, unknown>).temperature_2m;
  if (typeof temperature !== 'number' || !Number.isFinite(temperature) || (units as Record<string, unknown>).temperature_2m !== '°C') throw new WeatherError('The weather service did not return a valid temperature in °C. Please try again.');
  return temperature;
}

export async function fetchWeather(latitude: string, longitude: string, options: { signal?: AbortSignal; timeoutMs?: number; fetchImpl?: typeof fetch } = {}): Promise<WeatherResult> {
  const coordinates = parseCoordinates(latitude, longitude);
  const query = new URLSearchParams({ latitude: String(coordinates.latitude), longitude: String(coordinates.longitude), current: 'temperature_2m' });
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), options.timeoutMs ?? REQUEST_TIMEOUT_MS);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout.signal]) : timeout.signal;
  try {
    const response = await (options.fetchImpl ?? fetch)(`${WEATHER_ENDPOINT}?${query}`, { signal, credentials: 'omit', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new WeatherError(response.status === 429 ? 'The weather service is busy. Please wait a moment and try again.' : 'The weather service is temporarily unavailable. Please try again.');
    let body: unknown;
    try { body = await response.json(); }
    catch { throw new WeatherError('The weather service returned an unreadable response. Please try again.'); }
    return { ...coordinates, temperature: parseTemperature(body) };
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException('Request cancelled.', 'AbortError');
    if (timeout.signal.aborted) throw new WeatherError('The weather request timed out. Please try again.');
    if (error instanceof WeatherError) throw error;
    throw new WeatherError('Unable to reach the weather service. Check your internet connection and try again.');
  } finally { clearTimeout(timer); }
}
