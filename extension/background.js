importScripts('config.js');
const API = WATCHMYWORK.api;
function trustedDemo(value) {
  try { const url = new URL(value); return url.origin === WATCHMYWORK.demo && [WATCHMYWORK.weather, '/developer'].includes(url.pathname); } catch { return false; }
}
let queue = Promise.resolve();
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  const trusted = sender.id === chrome.runtime.id && (sender.url?.startsWith(chrome.runtime.getURL('')) || trustedDemo(sender.url));
  if (!trusted) return false;
  let path;
  let options = {};
  if (message.type === 'current') path = '/teach/current';
  else if (message.type === 'complete' && /^[a-f0-9]{32}$/.test(message.id)) {
    path = `/demos/${message.id}/stop`;
    options = { method: 'POST', headers: { 'X-WatchMyWork': 'local-demo' } };
  }
  else if (message.type === 'events' && /^[a-f0-9]{32}$/.test(message.id)) {
    path = `/demos/${message.id}/events`;
    options = { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-WatchMyWork': 'local-demo' }, body: JSON.stringify({ events: message.events }) };
  } else return false;
  // Serialize event batches so focus, fill, click and extraction stay in order.
  queue = queue.catch(() => {}).then(async () => {
    try {
      const response = await fetch(API + path, { ...options, signal: AbortSignal.timeout(5000) });
      const data = await response.json();
      respond(response.ok ? { ok: true, data } : { ok: false, error: typeof data.detail === 'string' ? data.detail : 'Recording could not be saved.' });
    } catch {
      respond({ ok: false, error: 'Backend is unavailable. Try again shortly.' });
    }
  });
  return true;
});
