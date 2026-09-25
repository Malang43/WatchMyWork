import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import vm from 'node:vm';
const local = dirname(fileURLToPath(import.meta.url));
const root = process.argv[2] ? resolve(local, process.argv[2]) : local;
const manifest = JSON.parse(readFileSync(join(root, 'manifest.json'), 'utf8'));
assert.equal(manifest.manifest_version, 3);
if (root === local) {
  const production = 'https://watchmywork-production.up.railway.app';
  assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1:8000/*', production + '/*']);
  assert.deepEqual(manifest.content_scripts[0].matches, ['http://127.0.0.1:5173/*', production + '/developer*', production + '/weather*']);
} else {
  assert.equal(manifest.host_permissions.length, 1);
  const origin = manifest.host_permissions[0].slice(0, -2);
  assert.equal(new URL(origin).origin, origin);
  assert.equal(new URL(origin).protocol, 'https:');
  assert.ok(!origin.includes('*'));
  assert.deepEqual(manifest.host_permissions, [origin + '/*']);
  assert.deepEqual(manifest.content_scripts[0].matches, [origin + '/developer*', origin + '/weather*']);
}
assert.deepEqual(manifest.permissions, ['storage']);
assert.ok(!manifest.permissions.includes('debugger'));
for (const file of [manifest.background.service_worker, ...manifest.content_scripts[0].js, 'popup.js']) execFileSync(process.execPath, ['--check', join(root, file)]);
assert.ok(existsSync(join(root, manifest.action.default_popup)));
// Exercise the actual worker: production senders must never reach localhost.
let listener;
const calls = [];
const context = vm.createContext({
  importScripts() {}, AbortSignal, URL,
  chrome: { runtime: { id: 'a'.repeat(32), getURL: () => 'chrome-extension://' + 'a'.repeat(32) + '/', onMessage: { addListener(fn) { listener = fn; } } } },
  fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({ state: 'complete' }) }; },
});
vm.runInContext(readFileSync(join(root, 'config.js'), 'utf8'), context);
vm.runInContext(readFileSync(join(root, 'background.js'), 'utf8'), context);
const settings = context.WATCHMYWORK;
async function send(url, message) {
  return new Promise(resolve => {
    if (!listener(message, { id: 'a'.repeat(32), url }, resolve)) resolve(null);
  });
}
for (const [origin, api] of [[settings.demo, settings.api], ...(settings.production ? [[settings.production, settings.production]] : [])]) {
  for (const message of [{ type: 'current' }, { type: 'events', id: 'b'.repeat(32), events: [] }, { type: 'complete', id: 'b'.repeat(32) }]) {
    assert.equal((await send(origin + '/developer?test=1', message)).ok, true);
    assert.ok(calls.at(-1).url.startsWith(api + '/'));
  }
}
for (const url of ['https://attacker.invalid/developer', (settings.production || settings.demo) + '/developer/unsupported']) {
  assert.equal(await send(url, { type: 'current' }), null);
}
console.log('Extension manifest, host restrictions, resources, and JavaScript syntax passed.');
