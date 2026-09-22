// 传感器框架 · **屏幕系约定**（唯一真值）。
//
// **为什么单独一个模块**：坞里的画布（深度帧 / 高度场 / 极坐标 / 点云 / 2D 轨迹）与两个相机
// 预览（RGB / 深度外挂）此前**各写各的朝向**。于是同一件事出现三种朝向口径：
//   · 深度：策略吃的那份（`pie_depth.js`）与外挂预览（`buildPattern("pinhole")`）差 **180°**；
//   · 深度外挂预览：又用装配 rpy 直接当基架，而 `[0,-80,0]` 这种"前视相机"的 rpy 自带
//     90° 滚转 ⇒ 预览里的地平线是**竖的**（用户报的"深度图被旋转过"就是它）；
//   · 高度场：187 格契约是 **x 主序**（index = i_x*11 + i_y），却被当作行主序铺进 17 宽的
//     图像 ⇒ 整张图**错位成噪声/斜条**（用户报的"雷达之类的图也是旋转过的"）。
// 朝向这类"数算对了、画画反了"的缺陷**不抛异常、不改变任何读数**，只有人眼能发现——
// 所以它必须**一处定义、处处取用**，并由 Node 单测钉住（单测里能断言"世界 +x 的点画在屏幕右侧"）。
//
// ---------------------------------------------------------------------------
// 一、相机系（透视图像：RGB 预览 / 深度帧 / 深度外挂预览）
// ---------------------------------------------------------------------------
//   · 光轴是局部 **−z**（MuJoCo 相机约定）；
//   · **图像右 = +x，图像上 = +y**；
//   · 帧数组**行优先**（`index = row*width + col`），**row 0 = 图像顶部、col 0 = 图像左侧**。
//
// **依据（本仓可核对的实证，不是记忆）**：
//   1. 右手系定理：相机系是右手系（`x × y = z`）且光轴为 `−z` 时，观察者的"右"只能是 +x、
//      "上"只能是 +y（取 up=+y 时 `right × up = back = +z` 成立；若强行取"+y 朝下"，则
//      right 必须为 −x，即"x 右 + y 下"是**左手系**，任何旋转都造不出来）。
//   2. `mujoco/rendering/classic/renderer.py::Renderer.render()` 对 EGL/OSMesa/GLFW 后端
//      显式做 `out[:] = np.flipud(out)`（GL 帧缓冲本来自下而上）⇒ 返回的图**第 0 行是顶部**。
//   3. 上游 PIE 深度相机 `CAM_QUAT=(0.5792280,0.4055798,−0.4055798,−0.5792280)`：其 x 轴 =
//      机身 −y（**正右**）、y 轴 ≈ 机身 +z（**正上**）⇒ 只有"右=x、上=y"才是**正立**图像，
//      与 2 一致（其光轴 ≈ (0.94, 0, −0.34)：前视、下俯 20°，正是跑酷深度相机该有的样子）。
//   ⇒ 像素 `(row=v, col=u)` 的相机系射线 = `normalize([px, −py, −1])`，
//     `px = (u + 0.5 − 0.5W)/focal`、`py = (v + 0.5 − 0.5H)/focal`。
//     **y 取负**：图像"上"是 +y，而行号 v 向下增长。
//
//   ⚠ 已核实的**上游分歧**（如实记，不照抄）：`mjlab/src/mjlab/sensor/raycast_sensor.py` 的
//   `PinholeCameraPatternCfg` 注释写 "−Z forward, +X right, +Y down"，并把 `ray_y` 直接取
//   `+grid_v`（第 0 行 `v=−1` 为负）。该注释与 1/2/3 三条冲突（"+x 右 + y 下"是左手系，且会
//   让上游自己的渲染图上下颠倒）。**本框架以真实渲染图像为准**，与上游 raycast pattern 的
//   这个差异记在此处；`pie_depth.js` 与 `adapters/mjlab/policy_acceptance.py` 的 PIE 射线
//   也按本文件对齐（此前它们的 x 符号相反 ⇒ 策略吃到的是**左右镜像**的深度图）。
//
// ---------------------------------------------------------------------------
// 二、平面画布系（俯视：极坐标 / 点云 / 2D 轨迹 / 高度场）
// ---------------------------------------------------------------------------
//   · 平面 **+x 画向屏幕右、+y 画向屏幕上**（canvas 的 y 轴天生向下，所以取负）。
//     与 rviz 的俯视口径一致，也与 3D 场景"从上往下看"的直观一致：机头（+x）在右、
//     机身左侧（+y）在上。
//   · 俯视网格（187 契约）的**值序**是 x 主序（`i = i_x*ny + i_y`，x、y 均升序），
//     铺进像素时必须显式换算（`gridIndexToPixel`）——**不能**直接当行主序贴图。

/** 世界/机体系的"上"（MuJoCo 约定：z 朝上）。相机基架与平面画布都用它定"哪边朝上"。 */
export const WORLD_UP = [0, 0, 1];

/** 相机系的三个轴（机体系表达）：−z 为光轴、+x 右、+y 上。 */
export const CAMERA_AXES = { fwd: [0, 0, -1], right: [1, 0, 0], up: [0, 1, 0] };

/** 垂直视场角（度）+ 图像高（像素）→ 焦距（像素）。MuJoCo 的 `cam_fovy` 同口径。 */
export function focalLength(height, fovyDeg) {
  const h = Math.max(1, Number(height) || 1);
  const fovy = (Math.max(1e-3, Number(fovyDeg) || 45) * Math.PI) / 180;
  return (0.5 * h) / Math.tan(fovy / 2);
}

function normalize3(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

function cross3(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/**
 * **针孔射线网格**（相机系，行优先）。
 *
 * 这是全项目**唯一**的"像素 → 射线"实现：`sensor_patterns.js::pinholePattern`（框架 pattern）、
 * 深度外挂预览、以及 PIE 深度（`pie_depth.js` / `policy_acceptance.py`，逐值同口径）都从它取语义。
 *
 * @returns {{offsets: number[][], directions: number[][], count: number, width: number, height: number,
 *            focal: number, fovy: number}}
 */
export function pinholeRays({ width = 16, height = 12, fovy = 45 } = {}) {
  const w = Math.max(1, Math.round(Number(width) || 1));
  const h = Math.max(1, Math.round(Number(height) || 1));
  const focal = focalLength(h, fovy);
  const offsets = [];
  const directions = [];
  for (let v = 0; v < h; v += 1) {
    // 行 0 是图像顶部 ⇒ 该行"上"方向分量为正 ⇒ 方向里取 −py。
    const py = (v + 0.5 - 0.5 * h) / focal;
    for (let u = 0; u < w; u += 1) {
      const px = (u + 0.5 - 0.5 * w) / focal;
      offsets.push([0, 0, 0]);
      directions.push(normalize3([px, -py, -1]));
    }
  }
  return { offsets, directions, count: w * h, width: w, height: h, focal, fovy: Number(fovy) || 45 };
}

/**
 * **相机基架**：给定光轴方向与世界上方向，返回 `{fwd, right, up}`（相机系三轴在世界系里的表达）。
 *
 * 装配 rpy **只定义"往哪看"**：滚转不参与（`right` 由 `fwd × worldUp` 定），这样"前视相机"
 * 不会因为 rpy 里那个 90° 滚转把地平线画成竖线。相机系满足 `right × up = −fwd`（z 轴朝后）。
 *
 * 光轴与世界上方向平行时（正朝下/正朝上）退化，改用世界 +y 兜底定 right，不返回 NaN。
 */
export function cameraBasis(fwd, worldUp = WORLD_UP) {
  const f = normalize3(fwd);
  if (Math.hypot(f[0], f[1], f[2]) < 1e-9) {
    // 光轴退化成零向量（传感器还没就绪时的兜底）：给一个"正前视"基准，绝不返回 NaN——
    // NaN 会顺着射线传进求交，最后表现成"图全黑"而看不出去是哪一步坏的。
    return { fwd: [1, 0, 0], right: [0, -1, 0], up: [0, 0, 1] };
  }
  const upRef = normalize3(worldUp);
  let right = cross3(f, upRef);
  if (Math.hypot(right[0], right[1], right[2]) < 1e-6) right = cross3(f, [0, 1, 0]);
  right = normalize3(right);
  const up = normalize3(cross3(right, f));
  return { fwd: f, right, up };
}

/** 相机系方向 → 世界系方向（`dir = x*right + y*up + z*(−fwd)`）。 */
export function rayFromBasis(basis, localDir) {
  const [x, y, z] = localDir;
  const back = [-basis.fwd[0], -basis.fwd[1], -basis.fwd[2]];
  return [
    x * basis.right[0] + y * basis.up[0] + z * back[0],
    x * basis.right[1] + y * basis.up[1] + z * back[1],
    x * basis.right[2] + y * basis.up[2] + z * back[2],
  ];
}

/** 平面系坐标 (x, y) → canvas 像素：**+x 向右、+y 向上**（canvas y 向下 ⇒ 取负）。 */
export function planeToCanvas(x, y, { cx = 0, cy = 0, scale = 1 } = {}) {
  return [cx + Number(x) * scale, cy - Number(y) * scale];
}

/** 极坐标（角度按 +x 起、绕 +z 逆时针；半径已换算成像素）→ canvas 像素。 */
export function polarToCanvas(angle, radiusPx, { cx = 0, cy = 0 } = {}) {
  const r = Number(radiusPx) || 0;
  const a = Number(angle) || 0;
  return [cx + Math.cos(a) * r, cy - Math.sin(a) * r];
}

/**
 * 俯视网格格号 → canvas 像素行列。
 *
 * 值序是 **x 主序**（`i = i_x*ny + i_y`，x/y 均升序、第 0 行是 x 最小），画布约定是
 * **+x 向右、+y 向上** ⇒ `col = i_x`、`row = ny − 1 − i_y`。
 * 把 x 主序的数组直接当行主序贴图会得到一张"看着像图"的错位图（本项目 2026-09-22 实测踩中）。
 */
export function gridIndexToPixel(ix, iy, nx, ny) {
  const cols = Math.max(1, Math.floor(Number(nx) || 0));
  const rows = Math.max(1, Math.floor(Number(ny) || 0));
  const cx = Math.min(cols - 1, Math.max(0, Math.floor(Number(ix) || 0)));
  const cy = Math.min(rows - 1, Math.max(0, Math.floor(Number(iy) || 0)));
  return { col: cx, row: rows - 1 - cy };
}
