import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
const local = dirname(fileURLToPath(import.meta.url));
const root = process.argv[2] ? resolve(local, process.argv[2]) : local;
const manifest = JSON.parse(readFileSync(join(root, 'manifest.json'), 'utf8'));
assert.equal(manifest.manifest_version, 3);
if (root === local) {
  assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1:8000/*']);
  assert.deepEqual(manifest.content_scripts[0].matches, ['http://127.0.0.1:5173/*']);
} else {
  assert.equal(manifest.host_permissions.length, 1);
  const origin = manifest.host_permissions[0].slice(0, -2);
  assert.equal(new URL(origin).origin, origin);
  assert.equal(new URL(origin).protocol, 'https:');
  assert.ok(!origin.includes('*'));
  assert.deepEqual(manifest.host_permissions, [origin + '/*']);
  assert.deepEqual(manifest.content_scripts[0].matches, [origin + '/developer', origin + '/weather']);
}
assert.deepEqual(manifest.permissions, ['storage']);
assert.ok(!manifest.permissions.includes('debugger'));
for (const file of [manifest.background.service_worker, ...manifest.content_scripts[0].js, 'popup.js']) execFileSync(process.execPath, ['--check', join(root, file)]);
assert.ok(existsSync(join(root, manifest.action.default_popup)));
console.log('Extension manifest, host restrictions, resources, and JavaScript syntax passed.');
