$js = @'
async page => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const out = {};
  for (const policy of ['go2-jump-69', 'go2-baseline-164k']) {
    const rec = { steps: [] };
    await page.goto(`http://127.0.0.1:8765/web/sim2sim/index.html?robot=unitree_go2&policy=${policy}&debug=1`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForFunction(() => {
      const d = window.__sim2simDebug;
      if (!d || !d.sample) return false;
      const s = d.sample();
      return s.policyEnabled === true && s.baseZ !== null;
    }, null, { timeout: 120000 });
    rec.boot = await page.evaluate(() => {
      const st = window.__sim2simDebug.state();
      return { mode: st.policyMode, inputs: st.policyInputs, obsDim: st.obsDim, hasPolicyInfo: st.policyHealth !== null };
    });
    for (let i = 0; i < 12; i += 1) {
      rec.steps.push(await page.evaluate(async () => {
        const d = window.__sim2simDebug;
        const s = await d.fastForward(0.25);
        const st = d.state();
        const absMax = a => (Array.isArray(a) ? a.reduce((m, v) => Math.max(m, Math.abs(v)), 0) : null);
        return {
          t: s.time, z: s.baseZ, qw: s.quat[0],
          actMax: Number(absMax(st.action).toFixed(3)),
          appliedMax: Number(absMax(st.appliedAction).toFixed(3)),
          obsMax: Number(absMax(st.obs).toFixed(2)),
          tpos0: Number(st.targetDofPos[0].toFixed(3)),
          def0: Number(st.defaultAngles[0].toFixed(3)),
        };
      }));
    }
    out[policy] = rec;
  }
  return JSON.stringify(out);
}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_probe_actions_result.json -Encoding utf8
