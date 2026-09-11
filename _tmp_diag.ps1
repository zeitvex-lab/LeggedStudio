$js = @'
async page => {
  await page.goto('http://127.0.0.1:8765/web/sim2sim/index.html?robot=unitree_go2&policy=go2-backflip-69&debug=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(() => window.__sim2simDebug && window.__sim2simDebug.sample && window.__sim2simDebug.sample().policyEnabled === true, null, { timeout: 90000 });
  await page.waitForTimeout(2000);
  const info = await page.evaluate(() => {
    const sel = document.getElementById('policySelect');
    return {
      urlPolicy: new URLSearchParams(location.search).get('policy'),
      selectValue: sel ? sel.value : null,
      selectOptions: sel ? Array.from(sel.options).map(o => o.value) : null,
      mode: window.__sim2simDebug.state ? 'has-state' : 'no-state',
    };
  });
  const s = await page.evaluate(() => window.__sim2simDebug.fastForward(2));
  return JSON.stringify({ info: info, sample: s });
}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_diag_result.json -Encoding utf8
