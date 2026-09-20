const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('app/src/main/assets/scan3d.html', 'utf8');
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)) new vm.Script(match[1]);
const code = html.slice(html.indexOf('function onGLBReady('), html.indexOf('function onGLBDownloadError('));
async function run(fetchImpl) {
  const state = { fetch: fetchImpl, finished: 0, errors: [], downloadedBuffer: null, downloadDone: false };
  state.tryFinishAnalysis = () => state.finished++;
  state.onGLBDownloadError = message => state.errors.push(message);
  vm.createContext(state);
  vm.runInContext(code, state);
  state.onGLBReady('https://appassets.androidplatform.net/model/current.glb');
  await new Promise(resolve => setImmediate(resolve));
  return state;
}
(async () => {
  const buffer = new ArrayBuffer(16);
  const ok = await run(async () => ({ ok: true, arrayBuffer: async () => buffer }));
  assert.equal(ok.downloadedBuffer, buffer);
  assert.equal(ok.downloadDone, true);
  assert.equal(ok.finished, 1);
  const http = await run(async () => ({ ok: false, status: 404 }));
  assert.equal(http.finished, 0);
  assert.match(http.errors[0], /404/);
  const network = await run(async () => { throw new Error('cancelled'); });
  assert.equal(network.downloadDone, false);
  assert.equal(network.errors[0], 'cancelled');
  console.log('3D inline JavaScript syntax and 3 binary-loading cases passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
