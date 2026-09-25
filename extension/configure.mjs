// Generate a separate unpacked production extension; retain the local extension.
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const origin = process.argv[2];
let url;
try { url = new URL(origin); } catch { throw new Error('Pass the final HTTPS Railway origin.'); }
if (url.protocol !== 'https:' || url.origin !== origin || url.port || url.username || url.password || !/^[a-zA-Z0-9.-]+$/.test(url.hostname)) {
  throw new Error('Use an exact HTTPS origin without a trailing slash, path, credentials or port.');
}
const output = join(root, '..', 'extension-production');
mkdirSync(output, { recursive: true });
const manifest = JSON.parse(readFileSync(join(root, 'manifest.json'), 'utf8'));
manifest.name = 'WatchMyWork — Production Teach Mode';
manifest.description = 'Record demonstrations on the configured WatchMyWork developer and weather demos.';
manifest.host_permissions = [origin + '/*'];
manifest.content_scripts[0].matches = [origin + '/developer*', origin + '/weather*'];
for (const file of ['background.js', 'recorder.js', 'popup.html', 'popup.js']) copyFileSync(join(root, file), join(output, file));
writeFileSync(join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
writeFileSync(join(output, 'config.js'), 'globalThis.WATCHMYWORK = Object.freeze(' + JSON.stringify({ api: origin, app: origin + '/', demo: origin, weather: '/weather' }) + ');\n');
console.log('Production extension prepared in extension-production/. Load or reload that folder in Chrome.');
