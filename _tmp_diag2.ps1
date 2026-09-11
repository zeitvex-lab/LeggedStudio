$js = @'
async page => {
  const out = {};
  try {
    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/simulation/browser-package/unitree_go2/simulation/policies/jump_motion.csv', { cache: 'no-store' });
      const text = await r.text();
      return { status: r.status, ct: r.headers.get('content-type'), len: text.length, head: text.slice(0, 80), lines: text.trim().split(/[\r\n]+/).length };
    });
    out.csv = resp;
  } catch (e) { out.csvErr = String(e); }
  return JSON.stringify(out);
}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_diag2_result.json -Encoding utf8
