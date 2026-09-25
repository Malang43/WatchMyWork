(() => {
  if (location.origin !== WATCHMYWORK.demo || ![WATCHMYWORK.weather, '/developer'].includes(location.pathname)) return;
  const dev = location.pathname === '/developer';
  let demo = null, pending = [], sending = false, saved = false, submitted = false, captured = false;
  let lastResult = '', previousText = '', resultChanged = false, lastValues = {}, clickPending = false;
  const fields = dev ? ['#email-input', '#password-input'] : ['#latitude-input', '#longitude-input'];
  const resultSelector = dev ? '#login-result' : '#temperature-result';
  const buttonSelector = dev ? '#login-button' : '#check-weather-button';
  const panel = document.createElement('aside');
  panel.id = 'watchmywork-recorder'; panel.setAttribute('aria-live', 'polite');
  Object.assign(panel.style, { position: 'fixed', right: '16px', bottom: '16px', zIndex: '2147483647', maxWidth: '320px', padding: '16px 20px', borderRadius: '12px', background: '#142c24', color: '#fff', boxShadow: '0 6px 24px #0003', font: '13px/1.5 Segoe UI, sans-serif' });
  document.body.appendChild(panel);
  function show(text) { if (panel.textContent !== text) panel.textContent = text; }
  function ready() {
    panel.dataset.recording = demo?.id || ''; panel.dataset.state = demo ? 'recording' : saved ? 'saved' : 'ready';
    show(demo ? dev ? 'Recording · Fill Email and Password, click Login, and wait for the result.' : '\u25cf Recording \u00b7 Enter Latitude and Longitude, click Check Weather, and wait for the temperature result.' : saved ? dev ? '✓ Test demonstration captured' : `\u2713 Demonstration saved \u00b7 Temperature captured: ${lastResult}` : 'WatchMyWork ready · Start Recording in the main app.');
  }
  function event(action, target, extra = {}) { if (!demo) return; pending.push({ action, target, url: location.origin + location.pathname, ...extra }); void flush(); }
  async function flush() {
    if (sending || !pending.length || !demo) return;
    sending = true; const batch = pending.splice(0, 50); let retry = false;
    try {
      const response = await chrome.runtime.sendMessage({ type: 'events', id: demo.id, events: batch });
      if (!response?.ok) throw new Error('Save failed');
      if (batch.some(e => e.action === 'extract')) {
        const completion = await chrome.runtime.sendMessage({ type: 'complete', id: demo.id });
        if (!completion?.ok) throw new Error('Save not acknowledged');
        saved = completion.data.state === 'complete'; demo = null; pending = []; ready();
        if (!saved) { panel.dataset.state = 'incomplete'; show('The example did not match the selected row. Start another demonstration using that row’s inputs.'); }
      }
    } catch { retry = true; pending.unshift(...batch); show('Save not confirmed. Check the local backend; we will retry.'); }
    finally { sending = false; if (!retry && pending.length) void flush(); }
  }
  function recordValue(input) {
    const target = '#' + input.id;
    if (!demo || captured || input.value === lastValues[target]) return;
    lastValues[target] = input.value; submitted = false; lastResult = '';
    event('fill', target, { value: input.value, label: input.labels?.[0]?.textContent?.trim() || '', role: 'textbox' });
  }
  document.addEventListener('focusin', e => { if (fields.some(s => e.target.matches?.(s))) event('focus', '#' + e.target.id, { role: 'textbox' }); }, true);
  document.addEventListener('change', e => { if (fields.some(s => e.target.matches?.(s))) recordValue(e.target); }, true);
  function beginLookup() {
    if (!demo || captured || !fields.every(s => document.querySelector(s))) return;
    fields.forEach(s => recordValue(document.querySelector(s)));
    previousText = document.querySelector(resultSelector)?.textContent?.trim() || ''; resultChanged = !previousText; submitted = true;
    event('click', buttonSelector, { label: dev ? 'Login' : 'Check Weather', role: 'button' });
    event('wait', resultSelector, { label: dev ? 'Login result' : 'Temperature result', role: 'status' });
    queueMicrotask(inspectResult); setTimeout(inspectResult, 0);
  }
  document.addEventListener('click', e => { if (!e.target.closest?.(buttonSelector)) return; clickPending = true; beginLookup(); setTimeout(() => { clickPending = false; }, 0); }, true);
  document.addEventListener('submit', e => { if (!clickPending && e.target.querySelector?.(buttonSelector)) beginLookup(); }, true);
  function inspectResult() {
    if (!demo || !submitted || captured) return;
    const text = document.querySelector(resultSelector)?.textContent?.trim() || '';
    if (text !== previousText) resultChanged = true;
    const match = text.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\u00b0C$/);
    if (resultChanged && (dev ? Boolean(text) : match && Number.isFinite(Number(match[1])))) {
      captured = true; lastResult = text; event('extract', resultSelector, { text, label: dev ? 'Login result' : 'Temperature result', role: 'status' });
    }
  }
  new MutationObserver(inspectResult).observe(document.body, { childList: true, subtree: true, characterData: true });
  async function poll() {
    try {
      if (pending.length) await flush(); if (sending || pending.length) return;
      const currentId = demo?.id; const response = await chrome.runtime.sendMessage({ type: 'current' });
      if (sending || pending.length || currentId !== demo?.id) return;
      if (!response?.ok) { show(response?.error || 'Backend unavailable'); return; }
      const next = response.data && (response.data.mode === 'developer') === dev ? response.data : null;
      if (next?.id !== demo?.id) {
        demo = next; pending = []; lastValues = {}; submitted = false; captured = false;
        if (demo) { saved = false; lastResult = ''; }
        ready(); if (demo) event('navigate', location.origin + location.pathname, { label: document.title, role: 'document' });
      } else if (!demo && panel.dataset.state !== 'incomplete') ready();
    } catch { show('Extension disconnected. Reload this tab to reconnect.'); }
  }
  ready(); void poll(); setInterval(poll, 1000);
})();
