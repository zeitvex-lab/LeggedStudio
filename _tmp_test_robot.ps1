$js = @'
async page => {
  const results = [];
  const policies = ['go2-backflip-69', 'go2-jump-69'];
  for (const pid of policies) {
    try {
      await page.goto('http://127.0.0.1:8765/web/sim2sim/index.html?robot=unitree_go2&policy=' + pid + '&debug=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForFunction(() => window.__sim2simDebug && window.__sim2simDebug.sample && window.__sim2simDebug.sample().policyEnabled === true, null, { timeout: 90000 });
      await page.waitForTimeout(1500);
      const s1 = await page.evaluate(() => window.__sim2simDebug.fastForward(3));
      await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW' })));
      const s2 = await page.evaluate(() => window.__sim2simDebug.fastForward(2));
      await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keyup', { code: 'KeyW' })));
      results.push({ pid: pid, standZ: s1.baseZ, standW: s1.quat[0], standT: s1.time, teleCmd: s2.cmd[0], vx: s2.bodyLinearVel[0], teleZ: s2.baseZ, teleW: s2.quat[0] });
    } catch (e) {
      results.push({ pid: pid, error: String(e).slice(0, 200) });
    }
  }
  return JSON.stringify(results);
}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_test_result.json -Encoding utf8
