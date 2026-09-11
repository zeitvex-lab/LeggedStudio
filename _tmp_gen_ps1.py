# -*- coding: utf-8 -*-
"""生成单机型批量实测 ps1（JS 全单引号，规避 PowerShell 原生参数传递吞双引号）。

测试协议：
  1. 站立：加载策略后 fastForward(3) → baseZ / quat.w
  2. 遥控：KeyW 按住 fastForward(2) → cmd / bodyLinearVel[0]
"""
from __future__ import annotations

import sys

robot = sys.argv[1]
policies = sys.argv[2].split(",")

js_policies = ", ".join(f"'{p}'" for p in policies)
js = f"""async page => {{
  const results = [];
  const policies = [{js_policies}];
  for (const pid of policies) {{
    try {{
      await page.goto('http://127.0.0.1:8765/web/sim2sim/index.html?robot={robot}&policy=' + pid + '&debug=1', {{ waitUntil: 'domcontentloaded', timeout: 60000 }});
      await page.waitForFunction(() => window.__sim2simDebug && window.__sim2simDebug.sample && window.__sim2simDebug.sample().policyEnabled === true, null, {{ timeout: 90000 }});
      await page.waitForTimeout(1500);
      const s1 = await page.evaluate(() => window.__sim2simDebug.fastForward(3));
      await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', {{ code: 'KeyW' }})));
      const s2 = await page.evaluate(() => window.__sim2simDebug.fastForward(2));
      await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keyup', {{ code: 'KeyW' }})));
      results.push({{ pid: pid, standZ: s1.baseZ, standW: s1.quat[0], standT: s1.time, teleCmd: s2.cmd[0], vx: s2.bodyLinearVel[0], teleZ: s2.baseZ, teleW: s2.quat[0] }});
    }} catch (e) {{
      results.push({{ pid: pid, error: String(e).slice(0, 200) }});
    }}
  }}
  return JSON.stringify(results);
}}"""

ps1 = f"""$js = @'
{js}
'@
playwright-cli run-code $js 2>&1 | Out-File -FilePath _tmp_test_result.json -Encoding utf8
"""
Path = __import__("pathlib").Path
out = Path(__file__).resolve().parent / "_tmp_test_robot.ps1"
out.write_text(ps1, encoding="utf-8")
print(f"written for {robot}: {policies}")
