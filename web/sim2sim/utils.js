/**
 * Pure utility functions for sim2sim.
 *
 * These functions have no dependency on app.js global state (CONFIG/sim/view/
 * input) and can be unit-tested independently. Extracted from app.js during
 * god-file modularization.
 */

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function escapeAttr(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "");
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
  ));
}

export function formatSigned(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

/**
 * 四元数 → (roll, pitch, yaw)，即 mjlab `euler_xyz_from_quat` 的同一约定。
 *
 * 入参是 **MuJoCo 的 (w, x, y, z)**（qpos 自由关节位姿段 / poseFromQpos 的
 * quat 数组），与本文件其余 quat_* 助手（quatRotateInverse / getGravityOrientation
 * / getLinearVelocityBody，全部 q[0]=w）以及 raycast.js 的 quatToMat 一致。
 *
 * 历史包袱：本函数曾按 three.js 的 (x, y, z, w) 解包，两个调用点
 * （captureImuSample 的 imu.rpy、updateSensorPanels 的位姿读数）传的都是
 * (w,x,y,z)，于是 roll↔yaw 互换、pitch 变号：lainlab_gait_47_hist10 /
 * lainlab_spring_47_hist10 观测的 euler_xyz 段（3/47 维）每帧都在喂错值，
 * 实测 trot 策略 2.7s 内倒地（同 checkpoint 在 mjlab 训练环境 vx=0.5 跟踪正常）。
 */
export function quatToRpy(q) {
  const w = q[0], x = q[1], y = q[2], z = q[3];
  const sinrCosp = 2 * (w * x + y * z);
  const cosrCosp = 1 - 2 * (x * x + y * y);
  const roll = Math.atan2(sinrCosp, cosrCosp);
  const sinp = 2 * (w * y - z * x);
  const pitch = Math.abs(sinp) >= 1 ? Math.sign(sinp) * Math.PI / 2 : Math.asin(sinp);
  const sinyCosp = 2 * (w * z + x * y);
  const cosyCosp = 1 - 2 * (y * y + z * z);
  const yaw = Math.atan2(sinyCosp, cosyCosp);
  return [roll, pitch, yaw];
}

export function quatRotateInverse(q, v) {
  const qw = q[0];
  const qv = [q[1], q[2], q[3]];
  const dot = qv[0] * v[0] + qv[1] * v[1] + qv[2] * v[2];
  const cross = [
    qv[1] * v[2] - qv[2] * v[1],
    qv[2] * v[0] - qv[0] * v[2],
    qv[0] * v[1] - qv[1] * v[0],
  ];
  const factor = 2 * qw * qw - 1;
  return [
    v[0] * factor - cross[0] * qw * 2 + qv[0] * dot * 2,
    v[1] * factor - cross[1] * qw * 2 + qv[1] * dot * 2,
    v[2] * factor - cross[2] * qw * 2 + qv[2] * dot * 2,
  ];
}

export function getGravityOrientation(quaternion) {
  const qw = quaternion[0];
  const qx = quaternion[1];
  const qy = quaternion[2];
  const qz = quaternion[3];
  return [
    2 * (-qz * qx + qw * qy),
    -2 * (qz * qy + qw * qx),
    1 - 2 * (qw * qw + qz * qz),
  ];
}

export function getLinearVelocityBody(quaternion, vx, vy, vz) {
  const qw = quaternion[0];
  const qx = quaternion[1];
  const qy = quaternion[2];
  const qz = quaternion[3];
  return [
    (1 - 2 * (qy * qy + qz * qz)) * vx + 2 * (qx * qy + qw * qz) * vy + 2 * (qx * qz - qw * qy) * vz,
    2 * (qx * qy - qw * qz) * vx + (1 - 2 * (qx * qx + qz * qz)) * vy + 2 * (qy * qz + qw * qx) * vz,
    2 * (qx * qz + qw * qy) * vx + 2 * (qy * qz - qw * qx) * vy + (1 - 2 * (qx * qx + qy * qy)) * vz,
  ];
}

export function enumValue(value) {
  if (typeof value === "number") return value;
  if (value && typeof value.value === "number") return value.value;
  return Number(value);
}

export function isEditableElement(target) {
  if (!target || typeof target.tagName !== "string") return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  return false;
}
