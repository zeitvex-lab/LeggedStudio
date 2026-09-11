$js = @'
async page => {
  const errors = [];
  const consoleMsgs = [];
  page.on('pageerror', e => errors.push(String(e && e.message || e)));
  page.on('console', m => { if (m.type() === 'error') consoleMsgs.push(m.text()); });
  await page.goto('http://127.0.0.1:8765/web/sim2sim/index.html?robot=unitree_go2&policy=go2-jump-69&debug=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);
  const out = { errors: errors, consoleErrors: consoleMsgs.slice(0, 6) };
  try {
    out.info = await page.evaluate(() => {
      const sel = document.getElementById('policySelect');
      return {
        urlPolicy: new URLSearchParams(location.search).get('policy'),
        selectValue: sel ? sel.value : null,
        selectOptions: sel ? Array.from(sel.options).map(o => o.value) : null,
      };
    });
  } catch (e) { out.infoErr = String(e); }
  try {
    out.csv = await page.evaluate(async () => {
      const r = await fetch('/api/simulation/browser-package/unitree_go2/simulation/policies/jump_motion.csv', { cache: 'no-store' });
      const t = await r.text();
      return { status: r.status, ct: r.headers.get('content-type'), len: t.length, lines: t.trim().split(/[\r\n]+/).length, head: t.slice(0, 60) };
    });
  } catch (e) { out.csvErr = String(e); }
  try { out.sample = await page.evaluate(() => window.__sim2simDebug ? window.__sim2simDebug.sample() : null); } catch (e) { out.sampleErr = String(e); }
  return JSON.stringify(out, null, 1);
}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_diag_jump_result.json -Encoding utf8
