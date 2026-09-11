$js = @'
async page => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const results = {};
  for (const policy of ['go2-backflip-69', 'go2-jump-69']) {
    const consoleErr = [];
    const badUrls = [];
    const onConsole = m => { if (m.type() === 'error') consoleErr.push(m.text().split('\n')[0].slice(0, 150)); };
    const onReq = r => { if (r.url().includes('browser-package//')) badUrls.push(r.url()); };
    page.on('console', onConsole);
    page.on('request', onReq);
    const rec = { trajectory: [] };
    try {
      await page.goto(`http://127.0.0.1:8765/web/sim2sim/index.html?robot=unitree_go2&policy=${policy}&debug=1`, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForFunction(() => {
        const d = window.__sim2simDebug;
        if (!d || !d.sample) return false;
        const s = d.sample();
        return s.policyEnabled === true && s.baseZ !== null;
      }, null, { timeout: 120000 });
      rec.obsDim = await page.evaluate(() => window.__sim2simDebug.state().obsDim);
      for (let i = 0; i < 8; i += 1) {
        const s = await page.evaluate(() => window.__sim2simDebug.fastForward(0.4));
        rec.trajectory.push({ t: s.time, z: s.baseZ, qw: s.quat ? s.quat[0] : null, qx: s.quat ? s.quat[1] : null, vx: s.bodyLinearVel ? s.bodyLinearVel[0] : null });
      }
      rec.final = await page.evaluate(() => window.__sim2simDebug.sample());
    } catch (e) {
      rec.fatal = String(e).split('\n')[0].slice(0, 220);
    }
    page.off('console', onConsole);
    page.off('request', onReq);
    rec.consoleErrors = Array.from(new Set(consoleErr)).slice(0, 4);
    rec.doubleSlashUrls = Array.from(new Set(badUrls)).slice(0, 2);
    results[policy] = rec;
  }
  return JSON.stringify(results);
}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_verify_motion_result.json -Encoding utf8
