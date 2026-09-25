import { StrictMode, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { fetchWeather, WeatherError } from './weather';
import type { WeatherResult } from './weather';
import './styles.css';
import { DeveloperPortal } from './DeveloperPortal';

function App() {
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [result, setResult] = useState<WeatherResult | null>(null);
  const [error, setError] = useState<WeatherError | null>(null);
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => activeRequest.current?.abort(), []);

  function changeCoordinate(field: 'latitude' | 'longitude', value: string) {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setLoading(false); setResult(null); setError(null);
    if (field === 'latitude') setLatitude(value);
    else setLongitude(value);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setResult(null); setError(null); setLoading(true);
    try {
      const weather = await fetchWeather(latitude, longitude, { signal: controller.signal });
      if (activeRequest.current === controller) setResult(weather);
    } catch (cause) {
      if (activeRequest.current === controller && !controller.signal.aborted) {
        const nextError = cause instanceof WeatherError ? cause : new WeatherError('Something went wrong. Please try again.');
        setError(nextError);
        if (nextError.field) document.getElementById(`${nextError.field}-input`)?.focus();
      }
    } finally {
      if (activeRequest.current === controller) { setLoading(false); activeRequest.current = null; }
    }
  }

  return <main>
    <header><a className="brand" href="/">WatchMyWork<span className="brand-dot">.</span></a><span className="badge">WEATHER DEMO</span></header>
    <section className="intro"><p className="eyebrow">CURRENT WEATHER</p><h1>A place on the map.<br />The temperature, now.</h1><p className="subtitle">Enter latitude and longitude to look up the current temperature.</p></section>
    <section className="card" aria-label="Weather lookup">
      <form id="weather-form" onSubmit={handleSubmit} noValidate>
        <div className="coordinate-fields">
          <div><label htmlFor="latitude-input">Latitude</label><input id="latitude-input" name="latitude" aria-label="Latitude" type="text" inputMode="decimal" autoComplete="off" spellCheck={false} required value={latitude} placeholder="33.6844" aria-invalid={error?.field === 'latitude'} aria-describedby={error?.field === 'latitude' ? 'latitude-hint weather-error' : 'latitude-hint'} onChange={event => changeCoordinate('latitude', event.target.value)} /><p className="hint" id="latitude-hint">Decimal degrees, from -90 to 90.</p></div>
          <div><label htmlFor="longitude-input">Longitude</label><input id="longitude-input" name="longitude" aria-label="Longitude" type="text" inputMode="decimal" autoComplete="off" spellCheck={false} required value={longitude} placeholder="73.0479" aria-invalid={error?.field === 'longitude'} aria-describedby={error?.field === 'longitude' ? 'longitude-hint weather-error' : 'longitude-hint'} onChange={event => changeCoordinate('longitude', event.target.value)} /><p className="hint" id="longitude-hint">Decimal degrees, from -180 to 180.</p></div>
        </div>
        <button id="check-weather-button" name="checkWeather" type="submit" aria-label="Check Weather" disabled={loading}>{loading ? 'Checking Weather…' : 'Check Weather'}</button>
        {error && <p className="error" id="weather-error" role="alert">{error.message}</p>}
      </form>
      <section id="weather-result" className="result" role="status" aria-label="Weather result" aria-live="polite" aria-atomic="true" aria-busy={loading} data-state={loading ? 'loading' : error ? 'error' : result ? 'success' : 'idle'}>
        <span className="result-caption">CURRENT TEMPERATURE</span>
        <output id="temperature-result" name="temperature" htmlFor="latitude-input longitude-input" aria-label="Current temperature in Celsius" data-temperature={result?.temperature} data-unit={result ? 'celsius' : undefined}>{result ? `${result.temperature} °C` : ''}</output>
        <p>{loading ? 'Fetching current weather from Open-Meteo…' : result ? `Coordinates: ${result.latitude}, ${result.longitude}` : error ? 'No temperature available. Check the message above and try again.' : 'Your temperature result will appear here.'}</p>
      </section>
    </section>
    <section className="example" aria-labelledby="example-title"><h2 id="example-title">Try Islamabad, Pakistan</h2><p>Latitude <code>33.6844</code><span aria-hidden="true"> · </span> Longitude <code>73.0479</code></p></section>
    <footer>Weather data by <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a>. No API key required. Coordinates are sent to Open-Meteo when you check.</footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<StrictMode>{location.pathname === '/developer' ? <DeveloperPortal /> : <App />}</StrictMode>);
