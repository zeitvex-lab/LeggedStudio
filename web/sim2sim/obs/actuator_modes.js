// 执行器**角色 / 控制模式**解析（单一真值）。
//
// ## 为什么单独成模块
//
// 同一段"关节名 → { role, control mode }"的推断原先存在于**多处**：`app.js::
// applyActuatorContract`（运行时真路径）、`tools/obs_crosscheck.mjs`（同状态对拍驱动的
// 浏览器侧，它把 `controlModes` 写死成全 `"position"`、`jointGroup` 写死成恒返回
// `"leg"`）、以及各测试假体。**实测代价（2026-09-22）**：对拍工具因此把 m20/b2w 两条
// `go2w_rl_sdk_57` 策略判成"浏览器↔验收器不一致"（`max|Δ| = 5.000e-02`，形状正是
// "轮位该清零、却给了 (q−default)×scale"）——而真因是**尺子少喂了一个输入**：
// 这两个包的轮关节是在 `simulation/config.json` 的 `control_modes` 里**逐关节**点名的
// （`{"fl_wheel_joint": "velocity", …}`），工具没读，于是浏览器侧把 4 个轮子当位置关节。
//
// 抽出来之后：`app.js` 与对拍工具**调用同一个函数**，输入（策略契约 / 机器人 control）
// 各按自己的运行路径取，**解析规则只有一份**。这样"两边不一致"才真的等于"实现不一致"。
//
// 判据（与 `adapters/mjlab/policy_acceptance.py::PackageContract.is_velocity_joint`
// 同源口径，改动必须两侧同步）：
//   ① 角色：策略契约 `actuator_roles[名]` 优先，否则按关节名推断（wheel/foot ⇒ wheel，
//      其余随 `defaultRole`）；② 模式：策略契约 `control_modes` 先**精确名**后**角色名**，
//      再退到机器人 `control.control_modes`（同样先名后角色），最后兜底
//      "wheel 角色 ⇒ velocity，其余 ⇒ position"；③ 非法值一律落 `position`（fail-safe，
//      不抛：一个拼错的模式名不该让整个仿真起不来）。

/** 键名小写化（契约里关节名大小写跨包不一致，比较前统一）。 */
export function normalizeNameMap(value) {
  const result = {};
  if (!value || typeof value !== "object") return result;
  for (const [key, item] of Object.entries(value)) result[String(key).toLowerCase()] = item;
  return result;
}

/** 按关节名推断角色（Morphology-agnostic：轮足/足端都归 `wheel`）。 */
export function jointGroup(jointName) {
  const name = String(jointName).toLowerCase();
  if (name.includes("wheel") || name.includes("foot")) return "wheel";
  if (name.includes("calf")) return "calf";
  if (name.includes("thigh")) return "thigh";
  return "hip";
}

/**
 * 逐关节解出 `{ roles, modes }`（长度 = actionDim，下标与动作序对齐）。
 *
 * @param {object} args
 * @param {number} args.actionDim        动作维数（= 关节数）
 * @param {string[]} args.jointOrder     动作序关节名（下标与动作对齐）
 * @param {(name: string) => string} args.jointGroup 关节名 → 角色组（wheel/hip/thigh/calf）
 * @param {object} [args.contractRoles]  策略契约 `actuator_roles`
 * @param {object} [args.contractModes]  策略契约 `control_modes`
 * @param {object} [args.robotModes]     机器人 `control.control_modes`
 * @param {string} [args.defaultRole]    非轮关节的兜底角色（缺省 leg）
 */
export function resolveActuatorRolesAndModes({
  actionDim,
  jointOrder,
  jointGroup,
  contractRoles,
  contractModes,
  robotModes,
  defaultRole = "leg",
}) {
  const rolesRaw = normalizeNameMap(contractRoles);
  const policyModes = normalizeNameMap(contractModes);
  const robotModeMap = normalizeNameMap(robotModes);
  const roles = [];
  const modes = [];
  for (let i = 0; i < actionDim; i += 1) {
    const name = String(jointOrder[i] || "").toLowerCase();
    const inferredRole = jointGroup(name) === "wheel" ? "wheel" : defaultRole;
    const role = String(rolesRaw[name] || inferredRole).toLowerCase();
    const mode = String(
      policyModes[name]
      || policyModes[role]
      || robotModeMap[name]
      || robotModeMap[role]
      || (role === "wheel" ? "velocity" : "position"),
    ).toLowerCase();
    roles.push(role);
    modes.push(["position", "velocity", "torque"].includes(mode) ? mode : "position");
  }
  return { roles, modes };
}
