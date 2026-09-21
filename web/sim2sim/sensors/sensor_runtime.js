// 传感器框架 · 运行时（把退化模型接进读数路径）。
//
// 分工：`sensor_noise.js` 是**模型**（纯函数、可复现），本模块是**装配**——按场景种子建一份
// 噪声注册表，并在"关"时原样透传。为什么要单独一层：app.js 里的读数路径有四五处
// （IMU 采样 / 测距扫描 / 深度帧 / 接触），每处各写一遍 `if (noise) ...` 必然漏；
// 收成四个函数后，接线是机械的，测试也只需覆盖这一层。
//
// **默认关**：历史读数全是理想值，默认打开会静默改变所有既有读数与策略表现——那正是本仓
// 要消灭的"静默假绿"。要开，就在坞里勾"传感器退化模型"，或在场景里声明。
//
// **种子决定可复现**：同一个场景种子 ⇒ 同一条噪声序列 ⇒ 两次跑同一场景的差异可归因到策略，
// 而不是传感器在抖。

import { createNoise } from "./sensor_noise.js";

/**
 * 建一份噪声注册表。
 *
 * @param {number} seed 场景种子（同一 seed 同一序列）
 * @param {boolean} enabled 是否启用（false 时四个 apply 全部原样透传）
 * @param {object} params 每类模型的参数覆盖（缺省用模型自己的默认值）
 */
export function createNoiseRegistry(seed = 0, enabled = false, params = {}) {
  if (!enabled) {
    return { enabled: false, seed: Number(seed) || 0, imu: null, range: null, depth: null, contact: null };
  }
  return {
    enabled: true,
    seed: Number(seed) || 0,
    imu: createNoise("imu", { seed, ...(params.imu || {}) }),
    range: createNoise("range", { seed, ...(params.range || {}) }),
    depth: createNoise("depth", { seed, ...(params.depth || {}) }),
    contact: createNoise("contact", { seed, ...(params.contact || {}) }),
  };
}

/** IMU 读数（三轴角速度 / 重力投影）：加偏置 + 白噪声。 */
export function applyImuNoise(registry, sample) {
  if (!registry?.enabled || !registry.imu || !Array.isArray(sample)) return sample;
  return registry.imu.apply(sample);
}

/** 测距类读数（数组，null = 未命中）：超量程记 miss、丢帧、量化。 */
export function applyRangeNoise(registry, distances) {
  if (!registry?.enabled || !registry.range || !Array.isArray(distances)) return distances;
  return registry.range.apply(distances);
}

/** 深度帧（一维数组）：miss → 截止距离、加性噪声、量化。 */
export function applyDepthNoise(registry, frame) {
  if (!registry?.enabled || !registry.depth || !Array.isArray(frame)) return frame;
  return registry.depth.apply(frame);
}

/** 接触（key = 足名，force = 接触力 N）：迟滞 + 漏检。 */
export function applyContactNoise(registry, key, force) {
  if (!registry?.enabled || !registry.contact) return force > 0;
  return registry.contact.apply(key, force);
}

/** 注册表的人类可读摘要（坞里显示"当前用哪套退化"）。 */
export function describeNoiseRegistry(registry) {
  if (!registry?.enabled) return "理想值（未启用退化模型）";
  const parts = [];
  if (registry.imu) parts.push("IMU 偏置+白噪声");
  if (registry.range) parts.push("测距 丢帧+量化");
  if (registry.depth) parts.push("深度 miss+噪声");
  if (registry.contact) parts.push("接触 迟滞+漏检");
  return `退化模型（seed=${registry.seed}）：${parts.join(" / ")}`;
}
