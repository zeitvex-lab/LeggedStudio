// `utils.js` 单测（`node web/sim2sim/utils.test.mjs`）。
//
// **为什么专门守 IMU 这一处**：MuJoCo 自由关节的 `qvel` 两段**不在同一坐标系**
// （线速度世界系、角速度机体系），"哪段要 Rᵀ"写错一处就废——而写错在 **yaw≈0 处完全看不出来**
// （R≈I，策略照走），只有把机器人转到 ~180° 才会炸（水平两轴翻号 ⇒ 角速度反馈成正反馈 ⇒
// 乱动失衡）。2026-09-22 用户报的就是这条，浏览器侧错了很久没人发现，因为：
//   · 单测原本只钉"分段顺序"，不钉**数值口径**；
//   · 验收器（Python）用的是正确口径 ⇒ 同一条策略"验收里稳、浏览器里歪"。
// 所以这里的第一组断言不是"值是多少"，而是**yaw 不变性**（同一个机体系读数，机器人转到
// 任何朝向都必须逐位相同）——那才是它本该有的性质。
import assert from "node:assert/strict";
import { imuSampleFromQpos, quatToRpy, quatRotateInverse } from "./utils.js";

const near = (a, b, eps = 1e-6) => Math.abs(a - b) < eps;
const arrNear = (a, b, eps = 1e-6) => a.length === b.length && a.every((v, i) => near(v, b[i], eps));

/** 绕 z 的纯偏航四元数（w,x,y,z）。 */
const yawQuat = (deg) => {
  const a = (deg * Math.PI) / 360;
  return [Math.cos(a), 0, 0, Math.sin(a)];
};

/** 世界系线速度 = R·v_body（纯偏航下就是平面旋转）。 */
const yawRotate = (deg, [vx, vy, vz]) => {
  const a = (deg * Math.PI) / 180;
  return [vx * Math.cos(a) - vy * Math.sin(a), vx * Math.sin(a) + vy * Math.cos(a), vz];
};

const qposWith = (deg) => [0, 0, 0.35, ...yawQuat(deg)];

// 1) **yaw 不变性（本文件的头号断言）**：同一机体系角速度，机器人转到任何朝向读数必须相同
{
  const omegaBody = [0.5, -1.1, 0.9];
  const samples = [0, 90, 180, 270].map((deg) =>
    imuSampleFromQpos(qposWith(deg), [0, 0, 0, ...omegaBody]));
  for (const [i, deg] of [90, 180, 270].entries()) {
    assert.ok(
      arrNear(samples[i + 1].angular, samples[0].angular, 1e-9),
      `yaw=${deg}° 的角速度读数必须与 yaw=0 逐位相同，实得 ${samples[i + 1].angular} vs ${samples[0].angular}`,
    );
  }
  // 注意容差：读数是 Float32（1e-7 量级的表示误差），别拿 1e-9 去卡
  assert.ok(arrNear(samples[0].angular, omegaBody, 1e-6), `角速度应原样透传机体系值，实得 ${samples[0].angular}`);
  // 双重旋转的**具体形态**（写死在这，防止有人"顺手加个 Rᵀ"又把 bug 加回来）：
  //   Rᵀ(180°)·ω = (−ωx, −ωy, ωz) —— 水平两轴翻号，正是抽风的形状
  assert.ok(!near(samples[2].angular[0], -0.5), "yaw=180° 时 ωx 不许被翻号");
  assert.ok(!near(samples[2].angular[1], 1.1), "yaw=180° 时 ωy 不许被翻号");
}

// 2) **线速度要转**：世界系 v = R·v_body ⇒ 采样（机体系）必须还原出 v_body，且与朝向无关
{
  const vBody = [0.6, 0.15, 0.02];
  for (const deg of [0, 90, 180, 270]) {
    const sample = imuSampleFromQpos(qposWith(deg), [...yawRotate(deg, vBody), 0, 0, 0]);
    assert.ok(arrNear(sample.linear, vBody, 1e-6),
      `yaw=${deg}° 机体系线速度必须是 ${vBody}，实得 ${sample.linear}`);
  }
}

// 3) 重力投影：直立时恒为 (0,0,-1)（与朝向无关），低头/侧倾时符号按约定
{
  for (const deg of [0, 90, 180, 270]) {
    const sample = imuSampleFromQpos(qposWith(deg), [0, 0, 0, 0, 0, 0]);
    assert.ok(arrNear(sample.gravity, [0, 0, -1], 1e-6), `yaw=${deg}° 直立重力应为 (0,0,-1)`);
  }
  const rolled = imuSampleFromQpos([0, 0, 0.35, ...yawQuat(0)], [0, 0, 0, 0, 0, 0]);
  assert.ok(near(rolled.gravity[2], -1, 1e-6));
}

// 4) rpy：纯偏航能被还原（0/±90/180），且不因 qvel 变化而变
{
  assert.ok(near(quatToRpy(yawQuat(90))[2], Math.PI / 2, 1e-9));
  assert.ok(near(quatToRpy(yawQuat(-90))[2], -Math.PI / 2, 1e-9));
  assert.ok(near(Math.abs(quatToRpy(yawQuat(180))[2]), Math.PI, 1e-6));
  const sample = imuSampleFromQpos(qposWith(90), [1, 2, 3, 4, 5, 6]);
  assert.ok(near(sample.rpy[2], Math.PI / 2, 1e-6), "rpy 只取决于姿态，与 qvel 无关");
}

// 5) 零状态：直立静止 ⇒ 四项全是"零"（角速度 0、线速度 0、重力 (0,0,-1)、rpy 0）
{
  const sample = imuSampleFromQpos([0, 0, 0.35, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0]);
  assert.ok(arrNear(sample.angular, [0, 0, 0]));
  assert.ok(arrNear(sample.linear, [0, 0, 0]));
  assert.ok(arrNear(sample.gravity, [0, 0, -1]));
  assert.ok(arrNear(sample.rpy, [0, 0, 0]));
  assert.ok(sample.angular instanceof Float32Array && sample.linear instanceof Float32Array,
    "返回**定长数组**（后续会被噪声模块逐项读，不能是别名视图）");
}

// 6) 与通用助手的一致性：linear 必须等于 Rᵀ·v_world（不是 R·v_world，也不是不转）
{
  const q = yawQuat(37);
  const world = [0.4, -0.9, 0.1];
  const sample = imuSampleFromQpos([0, 0, 0.3, ...q], [...world, 0, 0, 0]);
  assert.ok(arrNear(sample.linear, quatRotateInverse(q, world), 1e-6), "linear 走 Rᵀ");
  const wrong = yawRotate(37, world); // R·world —— 转了反方向
  assert.ok(!arrNear(sample.linear, wrong, 1e-6), "linear 不许是 R·v（方向反了）");
}

console.log("utils: 6 组断言全部通过 ✔");
