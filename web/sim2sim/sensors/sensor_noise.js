// 传感器框架 · 噪声与退化（纯函数、**可复现**）。
//
// 为什么现在才有：此前坞里每个传感器都是理想值——IMU 零漂、测距永不丢、深度没有 miss。
// 于是"仿真里读到 0.32 m 高度"和"实机上读到 0.32 m"不是一回事，而页面上看不出任何差别。
// 本模块把退化做成**显式、可关、可复现**的模型，逐项注明上游依据（凭什么是这个形式）。
//
// **可复现是硬要求**：同一个 seed 必须得到同一条噪声序列——否则"两次跑同一场景结果不同"
// 无法归因（是策略不稳定还是传感器在抖）。故自带线性同余发生器（LCG），不依赖 Math.random。

/** LCG（数值常量取 glibc 常用值）：同 seed 同序列，跨平台确定。 */
export function createRandom(seed = 0) {
  let state = (Number(seed) || 0) >>> 0 || 1;
  return function next() {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

/** 标准正态（Box–Muller，用 LCG 驱动；避免依赖 Math.random）。 */
export function createGaussian(random) {
  return function gaussian() {
    let u = 0;
    let v = 0;
    while (u === 0) u = random();
    while (v === 0) v = random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
}

/**
 * IMU 退化：**偏置 + 白噪声**（bias + white noise）。
 *
 * 上游依据：`newton/_src/sensors/sensor_imu.py` 的结构（bias 随机游走或常偏置 + 高斯白噪声）。
 * 偏置在**整个 episode 内固定**（一次上电的安装零偏），白噪声逐拍采样——这两件事分开，
 * 否则"每次都不同的零偏"会让同一策略的两次表现不可比。
 *
 * @param {{bias?: number[], noise?: number[], seed?: number}} cfg
 * @returns {{apply(sample: number[]): number[], bias: number[]}}
 */
export function createImuNoise({ bias = [0, 0, 0], noise = [0, 0, 0], seed = 0 } = {}) {
  const random = createRandom(seed);
  const gaussian = createGaussian(random);
  // 上电零偏：每个轴一次抽样，episode 内不变
  const biasVec = bias.map((scale) => (Number(scale) || 0) * gaussian());
  return {
    bias: biasVec,
    apply(sample) {
      return sample.map((value, index) => {
        const white = (Number(noise[index]) || 0) * gaussian();
        return (Number(value) || 0) + biasVec[index] + white;
      });
    },
  };
}

/**
 * 测距类退化：**量程截断 + 随机丢帧 + 量化**。
 *
 * 上游依据：robosuite `demos/demo_sensor_corruption.py` 的传感器损坏注入（dropout/量化），
 * 以及真实 TOF/LiDAR 的普遍行为（超量程记 miss 而非记最大值——记最大值会让"很远"和
 * "刚好在量程边缘"无法区分）。
 *
 * @returns {{apply(distances: (number|null)[]): (number|null)[]}}
 */
export function createRangeNoise({ maxDist = 12, dropRate = 0, quantization = 0, seed = 0 } = {}) {
  const random = createRandom(seed);
  const q = Math.max(0, Number(quantization) || 0);
  return {
    apply(distances) {
      return distances.map((d) => {
        if (d === null || d === undefined || d < 0) return null; // 未命中：保持 miss
        if (random() < (Number(dropRate) || 0)) return null; // 丢帧：谎称没读到
        if (d > maxDist) return null; // 超量程：miss（不记 maxDist）
        return q > 0 ? Math.round(d / q) * q : d;
      });
    },
  };
}

/**
 * 深度退化：**miss → 截止距离**、加性噪声、量化。
 *
 * 上游依据：`parkour_mjlab/.../observations.py::camera_depth` 的注释——"MuJoCo-Warp 在射线
 * 未命中时深度缓冲留 0，真实深度传输可能把同一情形记成 NaN/inf"；`habitat-sim` 的
 * `redwood-depth-dist-model.npy` 给的是真实深度噪声分布（本处用高斯近似，如实注明）。
 *
 * @returns {{apply(frame: number[]): number[]}}
 */
export function createDepthNoise({ missValue = 3.0, noise = 0, quantization = 0, seed = 0 } = {}) {
  const random = createRandom(seed);
  const gaussian = createGaussian(random);
  const q = Math.max(0, Number(quantization) || 0);
  return {
    apply(frame) {
      return frame.map((value) => {
        if (!Number.isFinite(value) || value <= 0) return missValue; // miss → 截止
        let out = value + (Number(noise) || 0) * gaussian();
        if (out < 0) out = 0;
        if (q > 0) out = Math.round(out / q) * q;
        return out;
      });
    },
  };
}

/**
 * 接触退化：**迟滞 + 偶发漏检**。
 *
 * 上游依据：mjlab `contact_sensor.py` 与真实足底开关的普遍行为（接触力有阈值带，
 * 不是"碰一下就真"）；漏检模拟坏点/线缆松动。
 */
export function createContactNoise({ threshold = 1.0, hysteresis = 0.2, missRate = 0, seed = 0 } = {}) {
  const random = createRandom(seed);
  const state = new Map();
  const base = Number(threshold) || 0;
  const band = Math.max(0, Number(hysteresis) || 0);
  return {
    /** @param {string} key @param {number} force 接触力（N） */
    apply(key, force) {
      const previous = state.get(key) === true;
      // 迟滞带：**进入**用 threshold，**保持**用 threshold − band（常规语义；
      // 写成"进入也要 +band"会把该报的接触吞掉——本框架第一版就这么错的，测试钉住）。
      const enter = previous ? base - band : base;
      let on = force >= enter;
      if (random() < (Number(missRate) || 0)) on = false; // 漏检：读到也不报
      state.set(key, on);
      return on;
    },
  };
}

/** 按名字造噪声器（未知名字返回 null；null = 该传感器默认理想）。 */
export function createNoise(kind, params = {}) {
  switch (kind) {
    case "imu": return createImuNoise(params);
    case "range": return createRangeNoise(params);
    case "depth": return createDepthNoise(params);
    case "contact": return createContactNoise(params);
    default: return null;
  }
}
