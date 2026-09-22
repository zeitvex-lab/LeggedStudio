// 传感器 3D 场景叠加层（Isaac 风格可视化）。
//
// **为什么单独一层**：主 three.js 场景里需要有形的传感器指示物——高度扫描的彩色命中球、
// LiDAR 的距离着色点云、足底接触的着地球、IMU 的坐标轴。它们不是被动模型（那由
// SENSOR_MODELS 管），而是**随仿真数据实时更新的指示层**——数据变了颜色/位置跟着变。
//
// 设计约束：
//   * 每个层用**一个** THREE.Points / Group，只改 attribute / position / color，不重建；
//   * 不可见时 `visible = false`（不画零尺寸三角形骗 GPU）；
//   * 脏标记：数据没变就不重传 attribute。

import * as THREE from "three";

/** 高度场命中点层：187 个彩球（Isaac 风格），按相对高度彩虹着色，未命中藏远处。 */
export function createHeightScanLayer(count) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  // 未命中的初始位置：藏到看不见的地方（z = -999），颜色黑
  positions.fill(0);
  for (let i = 0; i < count; i += 1) positions[i * 3 + 2] = -999;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    size: 0.035,
    vertexColors: true,
    sizeAttenuation: true,
    depthTest: true,
  });
  const points = new THREE.Points(geometry, material);
  points.visible = false;
  points.frustumCulled = false; // 点位置每帧变，包围球不可靠
  return points;
}

/** LiDAR 命中点层：距离着色的 3D 点云。 */
export function createLidarLayer(count) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  positions.fill(0);
  for (let i = 0; i < count; i += 1) positions[i * 3 + 2] = -999;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    size: 0.025,
    vertexColors: true,
    sizeAttenuation: true,
    depthTest: true,
  });
  const points = new THREE.Points(geometry, material);
  points.visible = false;
  points.frustumCulled = false;
  return points;
}

/** 足底接触层：四只脚各一个半透明球（着地绿 / 离地灰暗）。 */
export function createContactLayer(footNames) {
  const group = new THREE.Group();
  const spheres = new Map();
  const footGeometry = new THREE.SphereGeometry(0.035, 12, 8);
  for (const name of footNames) {
    const material = new THREE.MeshBasicMaterial({
      color: 0x64748b,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(footGeometry, material);
    mesh.visible = false;
    group.add(mesh);
    spheres.set(name, mesh);
  }
  group.visible = false;
  return { group, spheres };
}

/** IMU 装配位标记：三支箭头（AxisHelper 的细线在场景里几乎不可见——2026-09-22
 *  用户反馈"很差"）+ 白色基座球。RGB = XYZ，仍按坐标轴口径，只是看得清。 */
export function createImuAxes(size = 0.09) {
  const group = new THREE.Group();
  const make = (dir, color) => {
    const arrow = new THREE.ArrowHelper(
      new THREE.Vector3(dir[0], dir[1], dir[2]),
      new THREE.Vector3(0, 0, 0),
      size,
      color,
      size * 0.38, // 锥头长
      size * 0.2,  // 锥头半径
    );
    group.add(arrow);
  };
  make([1, 0, 0], 0xe4574c); // x 红
  make([0, 1, 0], 0x4cc06a); // y 绿
  make([0, 0, 1], 0x4c7de4); // z 蓝
  const base = new THREE.Mesh(
    new THREE.SphereGeometry(size * 0.2, 14, 10),
    new THREE.MeshBasicMaterial({ color: 0xf5f7fa, transparent: true, opacity: 0.9, depthWrite: false }),
  );
  group.add(base);
  group.visible = false;
  return group;
}

/** 单点测距层：装配方向的射线 + 命中点标记（2026-09-22 用户反馈：没特效）。
 *  命中 → 亮黄射线到命中点 + 黄球标记；未命中 → 暗灰射线到量程上限，无标记。 */
export function createRangefinderLayer() {
  const group = new THREE.Group();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(6), 3));
  const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
    color: 0xffd23f, transparent: true, opacity: 0.9,
  }));
  line.frustumCulled = false;
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(0.025, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0xffd23f, transparent: true, opacity: 0.95, depthWrite: false }),
  );
  group.add(line);
  group.add(marker);
  group.visible = false;
  return { group, line, marker };
}

/** 更新 Points 层的 positions + colors（增量写，不重建 geometry）。 */
export function updatePointsLayer(points, positions, colors) {
  const posAttr = points.geometry.getAttribute("position");
  const colAttr = points.geometry.getAttribute("color");
  if (!posAttr || !colAttr) return;
  const n = Math.min(positions.length / 3, colAttr.count);
  for (let i = 0; i < n; i += 1) {
    posAttr.setXYZ(i, positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);
    colAttr.setXYZ(i, colors[i * 3], colors[i * 3 + 1], colors[i * 3 + 2]);
  }
  posAttr.needsUpdate = true;
  colAttr.needsUpdate = true;
}
