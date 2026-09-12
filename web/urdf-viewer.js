/* Three.js robot workbench viewer for URDF and MJCF packages. */
(function () {
  'use strict';

  const THREE_URL = '/web/sim2sim/vendor/three/build/three.module.js';
  let THREE = null;
  let state = null;
  const geometryCache = new Map();
  let inertialRecords = [];

  function numbers(value, fallback = []) {
    const result = String(value || '').trim().split(/\s+/).filter(Boolean).map(Number);
    return result.length && result.every(Number.isFinite) ? result : fallback.slice();
  }

  function directChildren(element, selector) {
    return Array.from(element?.children || []).filter((child) => child.matches(selector));
  }

  function directChild(element, selector) {
    return directChildren(element, selector)[0] || null;
  }

  function cleanPath(value) {
    return String(value || '').replace(/\\/g, '/').replace(/^file:\/\//i, '').replace(/^\.\//, '');
  }

  function modelDirectory(filename) {
    const parts = cleanPath(filename).split('/');
    parts.pop();
    return parts.join('/');
  }

  function joinPath(...parts) {
    const result = [];
    parts.forEach((part) => cleanPath(part).split('/').forEach((token) => {
      if (!token || token === '.') return;
      if (token === '..') result.pop(); else result.push(token);
    }));
    return result.join('/');
  }

  function assetCandidates(assetPath, filename, assetDirectory = '') {
    const raw = cleanPath(assetPath).replace(/^package:\/\//i, '');
    const modelDir = modelDirectory(filename);
    const packageRelative = raw.includes('/') ? raw.split('/').slice(1).join('/') : raw;
    return [...new Set([
      joinPath(modelDir, assetDirectory, raw),
      joinPath(modelDir, raw),
      joinPath(modelDir, assetDirectory, packageRelative),
      joinPath(modelDir, packageRelative),
      raw,
      packageRelative,
    ].filter(Boolean))];
  }

  function localAsset(candidates, files) {
    const normalized = candidates.map((candidate) => candidate.toLowerCase());
    return (files || []).find((file) => {
      const path = cleanPath(file.webkitRelativePath || file.name).toLowerCase();
      return normalized.some((candidate) => path === candidate || path.endsWith(`/${candidate}`)) ||
        normalized.some((candidate) => path.endsWith(`/${candidate.split('/').pop()}`));
    });
  }

  async function fetchAsset(candidates, files, baseUrl, asText) {
    const local = localAsset(candidates, files);
    if (local) return asText ? local.text() : local.arrayBuffer();
    if (!baseUrl) return null;
    // Probe every candidate at once; serial tries cost a full round trip per
    // miss and robot packages reference meshes through several base paths.
    const attempts = candidates.map(async (candidate) => {
      const url = `${String(baseUrl).replace(/\/$/, '')}/${candidate.split('/').map(encodeURIComponent).join('/')}`;
      const response = await fetch(url, { cache: 'force-cache' });
      if (!response.ok) throw new Error(String(response.status));
      return asText ? response.text() : response.arrayBuffer();
    });
    try {
      return await Promise.any(attempts);
    } catch (_) {
      return null;
    }
  }

  function parseObj(text) {
    const vertices = [];
    const positions = [];
    String(text || '').split(/\r?\n/).forEach((line) => {
      const parts = line.trim().split(/\s+/);
      if (parts[0] === 'v' && parts.length >= 4) vertices.push([+parts[1], +parts[2], +parts[3]]);
      if (parts[0] !== 'f' || parts.length < 4) return;
      const face = parts.slice(1).map((token) => {
        const index = Number(token.split('/')[0]);
        return index < 0 ? vertices.length + index : index - 1;
      });
      for (let index = 1; index < face.length - 1; index += 1) {
        for (const vertex of [face[0], face[index], face[index + 1]]) {
          const xyz = vertices[vertex];
          if (xyz) positions.push(xyz[0], xyz[1], xyz[2]);
          else positions.push(0, 0, 0);
        }
      }
    });
    if (!positions.length) return null;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    return geometry;
  }

  function parseStl(buffer) {
    if (!buffer || buffer.byteLength < 15) return null;
    const view = new DataView(buffer);
    let positions = null;
    const isBinary = buffer.byteLength >= 84 && view.getUint32(80, true) * 50 + 84 === buffer.byteLength;
    if (isBinary) {
      // Decode straight into a typed array — per-float pushes into a plain
      // array dominate load time (and overflow the stack on spread) for big parts.
      const triangleCount = view.getUint32(80, true);
      positions = new Float32Array(triangleCount * 9);
      for (let triangle = 0; triangle < triangleCount; triangle += 1) {
        const src = 84 + triangle * 50 + 12;
        const dst = triangle * 9;
        for (let i = 0; i < 9; i += 1) {
          positions[dst + i] = view.getFloat32(src + i * 4, true);
        }
      }
    } else {
      const text = new TextDecoder().decode(buffer);
      positions = [];
      for (const match of text.matchAll(/vertex\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)/gi)) {
        positions.push(Number(match[1]), Number(match[2]), Number(match[3]));
      }
    }
    if (!positions || !positions.length) return null;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(positions instanceof Float32Array ? positions : new Float32Array(positions), 3),
    );
    geometry.computeVertexNormals();
    return geometry;
  }

  async function loadMesh(assetPath, context, scale = [1, 1, 1]) {
    const candidates = assetCandidates(assetPath, context.filename, context.assetDirectory);
    const cacheKey = `${candidates[0]}|${scale.join(',')}`.toLowerCase();
    const sharedKey = `${context.baseUrl}|${cacheKey}`;
    if (!geometryCache.has(sharedKey)) {
      geometryCache.set(sharedKey, (async () => {
        const extension = cleanPath(assetPath).split('.').pop().toLowerCase();
        const payload = await fetchAsset(candidates, context.files, context.baseUrl, extension === 'obj');
        const geometry = extension === 'obj' ? parseObj(payload) : (extension === 'stl' ? parseStl(payload) : null);
        if (!geometry) return null;
        geometry.scale(Number(scale[0]) || 1, Number(scale[1]) || 1, Number(scale[2]) || 1);
        geometry.computeBoundingBox();
        return geometry;
      })());
    }
    const pending = geometryCache.get(sharedKey);
    if (context.progressive) {
      const placeholder = makeFallbackGeometry();
      placeholder.userData = { replacement: pending };
      return placeholder;
    }
    const geometry = await pending;
    return geometry?.clone() || null;
  }

  function upgradeProgressiveMesh(mesh, context) {
    const pending = mesh.geometry?.userData?.replacement;
    if (!pending) return;
    context.pendingMeshes += 1;
    const generation = context.generation;
    const task = pending.then((geometry) => {
      if (!geometry || !state || state.generation !== generation || !mesh.parent) return;
      const placeholder = mesh.geometry;
      mesh.geometry = geometry.clone();
      placeholder.dispose();
      context.loadedMeshes += 1;
      window.dispatchEvent(new CustomEvent('robot-viewer-progress', { detail: { loaded: context.loadedMeshes, total: context.pendingMeshes } }));
    }).catch(() => { context.missingMeshes += 1; });
    context.pendingTasks.push(task);
  }

  function rgbaMaterial(rgba, role = 'visual') {
    const color = rgba?.length >= 3 ? new THREE.Color(rgba[0], rgba[1], rgba[2]) : new THREE.Color(role === 'collision' ? 0xf2a65a : 0xb8c4cc);
    // 资产用 rgba 的 alpha=0 表示「只参与物理、不渲染」（MuJoCo 语义）。官方 TRON1
    // 系列 MJCF 的碰撞体全部写成 rgba="0 0 1 0"，若照抄这个 alpha，整层碰撞体都会是
    // 全透明——点了「碰撞」也看不到。碰撞层是 viewer 的诊断叠加层，不透明度必须由
    // viewer 兜底（默认 0.32，上限 0.45），只沿用资产给的 rgb。
    const alpha = Number(rgba?.[3]);
    const opacity = role === 'collision'
      ? Math.min(alpha > 0 ? alpha : 0.32, 0.45)
      : (Number.isFinite(alpha) ? alpha : 1);
    return new THREE.MeshStandardMaterial({
      color,
      opacity,
      transparent: opacity < 0.999,
      roughness: role === 'collision' ? 0.8 : 0.56,
      metalness: role === 'collision' ? 0 : 0.12,
      depthWrite: opacity >= 0.999,
      side: THREE.DoubleSide,
    });
  }

  function makeFallbackGeometry() {
    return new THREE.BoxGeometry(0.035, 0.035, 0.035);
  }

  function applyQuaternion(object, element) {
    const quat = numbers(element?.getAttribute('quat'));
    if (quat.length === 4) {
      object.quaternion.set(quat[1], quat[2], quat[3], quat[0]).normalize();
      return;
    }
    const euler = numbers(element?.getAttribute('euler'));
    if (euler.length === 3) object.rotation.set(euler[0], euler[1], euler[2], 'XYZ');
  }

  function applyPose(object, element, positionAttribute = 'pos') {
    const position = numbers(element?.getAttribute(positionAttribute), [0, 0, 0]);
    object.position.set(position[0] || 0, position[1] || 0, position[2] || 0);
    applyQuaternion(object, element);
  }

  function urdfOrigin(object, element) {
    const origin = directChild(element, 'origin');
    const xyz = numbers(origin?.getAttribute('xyz'), [0, 0, 0]);
    const rpy = numbers(origin?.getAttribute('rpy'), [0, 0, 0]);
    object.position.set(xyz[0] || 0, xyz[1] || 0, xyz[2] || 0);
    object.rotation.set(rpy[0] || 0, rpy[1] || 0, rpy[2] || 0, 'ZYX');
  }

  function registerMesh(mesh, role) {
    mesh.userData.robotRole = role;
    mesh.castShadow = role === 'visual';
    mesh.receiveShadow = true;
    state.roles[role].push(mesh);
  }

  function registerHelper(object, role) {
    object.userData.robotRole = role;
    state.roles[role].push(object);
  }

  function principalInertia(tensor) {
    if (tensor.length < 3 || !tensor.every(Number.isFinite)) return null;
    if (tensor.length < 6 || tensor.slice(3).every((value) => Math.abs(value) < 1e-14)) {
      return { moments: tensor.slice(0, 3), rotation: new THREE.Quaternion() };
    }
    const [ixx, iyy, izz, ixy, ixz, iyz] = tensor;
    const matrix = [[ixx, ixy, ixz], [ixy, iyy, iyz], [ixz, iyz, izz]];
    const basis = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    for (let iteration = 0; iteration < 24; iteration += 1) {
      let p = 0;
      let q = 1;
      if (Math.abs(matrix[0][2]) > Math.abs(matrix[p][q])) [p, q] = [0, 2];
      if (Math.abs(matrix[1][2]) > Math.abs(matrix[p][q])) [p, q] = [1, 2];
      if (Math.abs(matrix[p][q]) < 1e-14) break;
      const angle = 0.5 * Math.atan2(2 * matrix[p][q], matrix[q][q] - matrix[p][p]);
      const cosine = Math.cos(angle);
      const sine = Math.sin(angle);
      const app = matrix[p][p];
      const aqq = matrix[q][q];
      const apq = matrix[p][q];
      matrix[p][p] = cosine * cosine * app - 2 * sine * cosine * apq + sine * sine * aqq;
      matrix[q][q] = sine * sine * app + 2 * sine * cosine * apq + cosine * cosine * aqq;
      matrix[p][q] = matrix[q][p] = 0;
      for (let index = 0; index < 3; index += 1) {
        if (index === p || index === q) continue;
        const aip = matrix[index][p];
        const aiq = matrix[index][q];
        matrix[index][p] = matrix[p][index] = cosine * aip - sine * aiq;
        matrix[index][q] = matrix[q][index] = sine * aip + cosine * aiq;
      }
      for (let row = 0; row < 3; row += 1) {
        const vip = basis[row][p];
        const viq = basis[row][q];
        basis[row][p] = cosine * vip - sine * viq;
        basis[row][q] = sine * vip + cosine * viq;
      }
    }
    const rotationMatrix = new THREE.Matrix4().set(
      basis[0][0], basis[0][1], basis[0][2], 0,
      basis[1][0], basis[1][1], basis[1][2], 0,
      basis[2][0], basis[2][1], basis[2][2], 0,
      0, 0, 0, 1,
    );
    return { moments: [matrix[0][0], matrix[1][1], matrix[2][2]], rotation: new THREE.Quaternion().setFromRotationMatrix(rotationMatrix) };
  }


  function computeInertiaBoxData(tensor, mass, maxSize) {
    // Gazebo-style equivalent uniform box (see robot_viewer/URDF-Studio):
    // principal moments inverted through I = m/12 (h² + d²) with plausibility
    // gates so placeholder or nonsensical links render nothing.
    if (!(mass > 0) || tensor.length < 3 || !tensor.every(Number.isFinite)) return null;
    if (tensor.slice(0, 3).every((value) => Math.abs(value) < 1e-12)) return null;
    const principal = principalInertia(tensor);
    if (!principal) return null;
    const [ix, iy, iz] = principal.moments;
    if (![ix, iy, iz].every((value) => Number.isFinite(value))) return null;
    const factor = 6 / mass;
    const dim = (a, b, c) => Math.sqrt(Math.max(Math.abs(factor * (a + b - c)), 1e-6));
    let width = dim(iy, iz, ix);
    let height = dim(ix, iz, iy);
    let depth = dim(ix, iy, iz);
    // Plausibility: characteristic inertia radius far above the box implies a
    // placeholder link; density far below implies nonsense parameters.
    const avgMoment = (Math.abs(ix) + Math.abs(iy) + Math.abs(iz)) / 3;
    const inertiaRadius = Math.sqrt(avgMoment / mass);
    const avgBox = (width + height + depth) / 3;
    if (inertiaRadius > avgBox) return null;
    if ((mass / Math.max(width * height * depth, 1e-9)) < 1e-4) return null;
    const minSize = 0.005;
    width = Math.max(minSize, Math.min(width, 2.0));
    height = Math.max(minSize, Math.min(height, 2.0));
    depth = Math.max(minSize, Math.min(depth, 2.0));
    if (maxSize > 0) {
      width = Math.min(width, maxSize * 2);
      height = Math.min(height, maxSize * 2);
      depth = Math.min(depth, maxSize * 2);
    }
    return { width, height, depth, rotation: principal.rotation, moments: principal.moments };
  }

  function addMassProperties(parent, mass, tensor, applyOrigin, maxSize, linkName) {
    if (!(mass > 0)) return;
    const box = computeInertiaBoxData(tensor, mass, maxSize);
    if (box) {
      // Semi-transparent cyan box on the principal axes (URDF-Studio style).
      const inertia = new THREE.Group();
      applyOrigin(inertia);
      const geometry = new THREE.BoxGeometry(box.width, box.height, box.depth);
      const fill = new THREE.Mesh(
        geometry,
        new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.22, depthWrite: false }),
      );
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.6 }),
      );
      const holder = new THREE.Group();
      holder.quaternion.copy(box.rotation);
      holder.add(fill);
      holder.add(edges);
      inertia.add(holder);
      inertia.visible = false;
      parent.add(inertia);
      registerHelper(inertia, 'inertial');
    }
    // Blender-style quarter black/white sphere marks the centre of mass.
    const center = new THREE.Group();
    applyOrigin(center);
    const quadrantRadius = 0.008;
    const segments = 16;
    for (let quadrant = 0; quadrant < 8; quadrant += 1) {
      const phiStart = (quadrant % 4) * (Math.PI / 2);
      const thetaStart = quadrant < 4 ? 0 : Math.PI / 2;
      const white = (quadrant % 2 === 0) === (quadrant < 4);
      const quadrantMesh = new THREE.Mesh(
        new THREE.SphereGeometry(quadrantRadius, segments, segments, phiStart, Math.PI / 2, thetaStart, Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: white ? 0xffffff : 0x1a1a1e, depthTest: false }),
      );
      quadrantMesh.renderOrder = 21;
      center.add(quadrantMesh);
    }
    center.visible = false;
    parent.add(center);
    registerHelper(center, 'centerOfMass');
    if (linkName) {
      inertialRecords.push({
        link: linkName,
        mass,
        com: [center.position.x, center.position.y, center.position.z].map((value) => Number(value.toFixed(7))),
        principal: box ? box.moments.map((value) => Number(value.toPrecision(6))) : null,
      });
    }
  }

  function addJointAxis(parent, axis) {
    const helper = new THREE.ArrowHelper(axis.clone().normalize(), new THREE.Vector3(), 0.12, 0x1677c8, 0.035, 0.022);
    helper.visible = false;
    helper.userData.setRobotScale = (radius) => helper.setLength(Math.max(0.04, radius * 0.24), Math.max(0.015, radius * 0.065), Math.max(0.01, radius * 0.04));
    parent.add(helper);
    registerHelper(helper, 'jointAxes');
  }

  async function urdfGeometry(geometryElement, context) {
    const box = directChild(geometryElement, 'box');
    const sphere = directChild(geometryElement, 'sphere');
    const cylinder = directChild(geometryElement, 'cylinder');
    const mesh = directChild(geometryElement, 'mesh');
    if (box) {
      const size = numbers(box.getAttribute('size'), [0.08, 0.08, 0.08]);
      return new THREE.BoxGeometry(size[0], size[1], size[2]);
    }
    if (sphere) return new THREE.SphereGeometry(Math.max(Number(sphere.getAttribute('radius')) || 0.04, 0.001), 24, 16);
    if (cylinder) {
      const radius = Math.max(Number(cylinder.getAttribute('radius')) || 0.03, 0.001);
      const length = Math.max(Number(cylinder.getAttribute('length')) || 0.08, 0.001);
      const result = new THREE.CylinderGeometry(radius, radius, length, 24);
      result.rotateX(Math.PI / 2);
      return result;
    }
    if (mesh) {
      const scale = numbers(mesh.getAttribute('scale'), [1, 1, 1]);
      return loadMesh(mesh.getAttribute('filename') || mesh.getAttribute('url'), context, scale);
    }
    return null;
  }

  async function addUrdfBody(linkElement, group, role, context, globalMaterials) {
    const entries = directChildren(linkElement, role);
    await Promise.all(entries.map(async (entry) => {
      const geometryElement = directChild(entry, 'geometry');
      // Same collision deferral as the MJCF path: hidden by default, so the
      // mesh download waits until the layer is switched on.
      const isDeferred = role === 'collision'
        && context.deferCollision
        && Boolean(geometryElement?.querySelector('mesh'));
      const geometry = isDeferred ? makeFallbackGeometry() : await urdfGeometry(geometryElement, context);
      if (!geometry) {
        context.missingMeshes += 1;
        return;
      }
      const materialElement = directChild(entry, 'material');
      const colorElement = directChild(materialElement, 'color');
      const rgba = numbers(colorElement?.getAttribute('rgba'));
      const inherited = globalMaterials.get(materialElement?.getAttribute('name'));
      const mesh = new THREE.Mesh(geometry, rgbaMaterial(rgba.length ? rgba : inherited, role));
      if (isDeferred) {
        deferCollisionMesh(mesh, context, () => urdfGeometry(geometryElement, context));
      } else {
        upgradeProgressiveMesh(mesh, context);
      }
      urdfOrigin(mesh, entry);
      group.add(mesh);
      registerMesh(mesh, role);
    }));
  }

  function deferCollisionMesh(mesh, context, loader) {
    // Park a tiny stand-in geometry and record how to build the real one.
    mesh.visible = false;
    const generation = context.generation;
    context.deferredCollision.push(async () => {
      let real = await loader();
      // 延迟任务执行时 progressive 模式仍然生效：loadMesh 返回的是占位小盒，
      // 真实几何挂在 userData.replacement 的共享 promise 上，必须等它完成，
      // 否则 mesh 型碰撞体（如 tron1_sf 的足端）会永远停在占位盒上。
      if (real?.userData?.replacement) {
        const settled = await real.userData.replacement.catch(() => null);
        real = settled ? settled.clone() : null;
      }
      if (!state || state.generation !== generation || !mesh.parent || !real) return;
      mesh.geometry.dispose();
      mesh.geometry = real;
      mesh.visible = state.visibility.collision;
    });
  }

  function addUrdfMassProperties(linkElement, group) {
    const inertial = directChild(linkElement, 'inertial');
    if (!inertial) return;
    const mass = Number(directChild(inertial, 'mass')?.getAttribute('value'));
    const tensor = directChild(inertial, 'inertia');
    const components = ['ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz'].map((name) => Number(tensor?.getAttribute(name) || 0));
    const bounds = new THREE.Box3().setFromObject(group);
    const maxSize = bounds.isEmpty() ? 0 : Math.max(...bounds.getSize(new THREE.Vector3()).toArray());
    addMassProperties(group, mass, components, (object) => urdfOrigin(object, inertial), maxSize, linkElement.getAttribute('name'));
  }

  async function parseUrdf(documentNode, context) {
    const robot = documentNode.querySelector('robot');
    if (!robot) throw new Error('URDF root element is missing');
    const globalMaterials = new Map();
    directChildren(robot, 'material').forEach((materialElement) => {
      const rgba = numbers(directChild(materialElement, 'color')?.getAttribute('rgba'));
      if (rgba.length) globalMaterials.set(materialElement.getAttribute('name'), rgba);
    });
    const links = directChildren(robot, 'link');
    const jointElements = directChildren(robot, 'joint');
    const linkGroups = new Map();
    await Promise.all(links.map(async (link) => {
      const group = new THREE.Group();
      group.name = link.getAttribute('name') || 'link';
      group.userData.robotLink = group.name;
      linkGroups.set(group.name, group);
      await Promise.all([
        addUrdfBody(link, group, 'visual', context, globalMaterials),
        addUrdfBody(link, group, 'collision', context, globalMaterials),
      ]);
      addUrdfMassProperties(link, group);
    }));
    const children = new Set();
    jointElements.forEach((element) => {
      const name = element.getAttribute('name') || 'joint';
      const type = element.getAttribute('type') || 'fixed';
      const parentName = directChild(element, 'parent')?.getAttribute('link');
      const childName = directChild(element, 'child')?.getAttribute('link');
      const parent = linkGroups.get(parentName);
      const child = linkGroups.get(childName);
      if (!child) return;
      children.add(childName);
      const jointGroup = new THREE.Group();
      jointGroup.name = name;
      urdfOrigin(jointGroup, element);
      jointGroup.add(child);
      (parent || state.root).add(jointGroup);
      if (type === 'fixed' || type === 'floating' || type === 'planar') return;
      const axis = numbers(directChild(element, 'axis')?.getAttribute('xyz'), [1, 0, 0]);
      const axisVector = new THREE.Vector3(...axis).normalize();
      addJointAxis(jointGroup, axisVector);
      const limit = directChild(element, 'limit');
      const lower = type === 'continuous' ? -Math.PI : Number(limit?.getAttribute('lower'));
      const upper = type === 'continuous' ? Math.PI : Number(limit?.getAttribute('upper'));
      state.joints.set(name, {
        name,
        type,
        object: jointGroup,
        axis: axisVector,
        originQuaternion: jointGroup.quaternion.clone(),
        originPosition: jointGroup.position.clone(),
        lower: Number.isFinite(lower) ? lower : -Math.PI,
        upper: Number.isFinite(upper) ? upper : Math.PI,
        value: 0,
      });
    });
    linkGroups.forEach((group, name) => { if (!children.has(name)) state.root.add(group); });
    return { links: links.length, format: 'urdf' };
  }

  function mergeDefaults(target, source) {
    if (!source) return target;
    ['geom', 'joint'].forEach((kind) => { if (source[kind]) target[kind] = { ...(target[kind] || {}), ...source[kind] }; });
    return target;
  }

  function parseMjcfDefaults(root) {
    const classes = new Map();
    const base = {};
    function visit(element, parent) {
      const current = mergeDefaults({}, parent);
      ['geom', 'joint'].forEach((kind) => {
        const child = directChild(element, kind);
        if (child) current[kind] = { ...(current[kind] || {}), ...Object.fromEntries(Array.from(child.attributes).map((attribute) => [attribute.name, attribute.value])) };
      });
      const name = element.getAttribute('class');
      if (name) classes.set(name, current); else mergeDefaults(base, current);
      directChildren(element, 'default').forEach((child) => visit(child, current));
    }
    directChildren(root, 'default').forEach((element) => visit(element, base));
    return { base, classes };
  }

  function resolvedAttributes(element, kind, defaults, inheritedClass) {
    const result = { ...(defaults.base[kind] || {}) };
    const className = element.getAttribute('class') || inheritedClass;
    Object.assign(result, defaults.classes.get(className)?.[kind] || {});
    Array.from(element.attributes).forEach((attribute) => { result[attribute.name] = attribute.value; });
    return result;
  }

  function mjcfRole(attributes) {
    const className = String(attributes.class || '').toLowerCase();
    // 与 robot_viewer 对齐：显式 class/group 优先，网格 geom 名含 collision
    // （如 ankle_collision）作为兜底判为碰撞体。
    if (className.includes('visual') || Number(attributes.group) === 2) return 'visual';
    if (className.includes('collision') || Number(attributes.group) === 3) return 'collision';
    if (attributes.mesh && Number(attributes.contype || 0) === 0 && Number(attributes.conaffinity || 0) === 0) return 'visual';
    if (String(attributes.name || '').toLowerCase().includes('collision')) return 'collision';
    return attributes.mesh ? 'visual' : 'collision';
  }

  async function mjcfGeometry(attributes, assets, context) {
    const type = attributes.type || (attributes.mesh ? 'mesh' : 'sphere');
    const size = numbers(attributes.size, [0.03]);
    if (type === 'mesh') {
      const asset = assets.meshes.get(attributes.mesh);
      if (!asset) return null;
      return loadMesh(asset.file, context, asset.scale);
    }
    if (type === 'box') return new THREE.BoxGeometry(2 * (size[0] || 0.03), 2 * (size[1] || size[0] || 0.03), 2 * (size[2] || size[0] || 0.03));
    if (type === 'sphere') return new THREE.SphereGeometry(Math.max(size[0] || 0.03, 0.001), 24, 16);
    if (type === 'ellipsoid') {
      const result = new THREE.SphereGeometry(1, 24, 16);
      result.scale(size[0] || 0.03, size[1] || size[0] || 0.03, size[2] || size[0] || 0.03);
      return result;
    }
    if (type === 'cylinder' || type === 'capsule') {
      const radius = Math.max(size[0] || 0.02, 0.001);
      const halfLength = Math.max(size[1] || radius, 0.001);
      let result;
      if (type === 'capsule' && THREE.CapsuleGeometry) result = new THREE.CapsuleGeometry(radius, 2 * halfLength, 6, 16);
      else result = new THREE.CylinderGeometry(radius, radius, 2 * halfLength, 24);
      result.rotateX(Math.PI / 2);
      return result;
    }
    if (type === 'plane') return new THREE.PlaneGeometry(Math.max(size[0] * 2 || 4, 0.1), Math.max(size[1] * 2 || 4, 0.1));
    return makeFallbackGeometry();
  }

  function parseMjcfAssets(root) {
    const meshes = new Map();
    const materials = new Map();
    root.querySelectorAll('asset > mesh').forEach((element) => meshes.set(element.getAttribute('name') || cleanPath(element.getAttribute('file')).split('/').pop().replace(/\.[^.]+$/, ''), {
      file: element.getAttribute('file'),
      scale: numbers(element.getAttribute('scale'), [1, 1, 1]),
    }));
    root.querySelectorAll('asset > material').forEach((element) => materials.set(element.getAttribute('name'), numbers(element.getAttribute('rgba'))));
    return { meshes, materials };
  }

  function fromToPose(mesh, attributes) {
    const fromTo = numbers(attributes.fromto);
    if (fromTo.length !== 6) return false;
    const start = new THREE.Vector3(fromTo[0], fromTo[1], fromTo[2]);
    const end = new THREE.Vector3(fromTo[3], fromTo[4], fromTo[5]);
    const direction = end.clone().sub(start);
    mesh.position.copy(start.add(end).multiplyScalar(0.5));
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction.normalize());
    return true;
  }

  async function addMjcfGeoms(bodyElement, content, inheritedClass, defaults, assets, context) {
    await Promise.all(directChildren(bodyElement, 'geom').map(async (element) => {
      const attributes = resolvedAttributes(element, 'geom', defaults, inheritedClass);
      const role = mjcfRole(attributes);
      // Collision shells are hidden by default; skip their mesh downloads and
      // fill them in only when the user turns the collision layer on.
      const wantsMesh = Boolean(attributes.mesh) && (attributes.type || (attributes.mesh ? 'mesh' : 'sphere')) === 'mesh';
      const defer = role === 'collision' && context.deferCollision && wantsMesh && assets.meshes.has(attributes.mesh);
      let geometry = null;
      if (defer) geometry = makeFallbackGeometry();
      else geometry = await mjcfGeometry(attributes, assets, context);
      if (!geometry) {
        context.missingMeshes += 1;
        return;
      }
      const rgba = numbers(attributes.rgba);
      const materialRgba = assets.materials.get(attributes.material);
      const mesh = new THREE.Mesh(geometry, rgbaMaterial(rgba.length ? rgba : materialRgba, role));
      if (defer) {
        deferCollisionMesh(mesh, context, () => mjcfGeometry(attributes, assets, context));
      } else {
        upgradeProgressiveMesh(mesh, context);
      }
      if (!fromToPose(mesh, attributes)) applyPose(mesh, element);
      mesh.name = attributes.name || attributes.mesh || 'geom';
      content.add(mesh);
      registerMesh(mesh, role);
    }));
  }

  function addMjcfMassProperties(bodyElement, content, linkName) {
    const inertial = directChild(bodyElement, 'inertial');
    if (!inertial) return;
    const mass = Number(inertial.getAttribute('mass'));
    const diagonal = numbers(inertial.getAttribute('diaginertia'));
    const full = numbers(inertial.getAttribute('fullinertia'));
    const tensor = diagonal.length >= 3 ? diagonal.slice(0, 3) : full.slice(0, 6);
    const bounds = new THREE.Box3().setFromObject(content);
    const maxSize = bounds.isEmpty() ? 0 : Math.max(...bounds.getSize(new THREE.Vector3()).toArray());
    addMassProperties(content, mass, tensor, (object) => applyPose(object, inertial), maxSize, linkName);
  }

  async function parseMjcfBody(element, parent, inheritedClass, defaults, assets, context) {
    const bodyClass = element.getAttribute('childclass') || inheritedClass;
    const base = new THREE.Group();
    base.name = element.getAttribute('name') || 'body';
    base.userData.robotLink = base.name;
    applyPose(base, element);
    parent.add(base);

    const jointElements = directChildren(element, 'joint').filter((joint) => (joint.getAttribute('type') || 'hinge') !== 'free');
    let content = base;
    jointElements.forEach((jointElement, jointIndex) => {
      const attributes = resolvedAttributes(jointElement, 'joint', defaults, bodyClass);
      const name = attributes.name || `${base.name}_joint_${jointIndex + 1}`;
      const type = attributes.type || 'hinge';
      const axisValues = numbers(attributes.axis, [0, 0, 1]);
      const jointPosition = numbers(attributes.pos, [0, 0, 0]);
      const pivot = new THREE.Group();
      const offset = new THREE.Group();
      pivot.name = name;
      pivot.position.set(...jointPosition);
      offset.position.set(-jointPosition[0], -jointPosition[1], -jointPosition[2]);
      pivot.add(offset);
      content.add(pivot);
      content = offset;
      if (type === 'hinge' || type === 'slide') {
        const range = numbers(attributes.range);
        const axis = new THREE.Vector3(...axisValues).normalize();
        addJointAxis(pivot, axis);
        state.joints.set(name, {
          name,
          type: type === 'slide' ? 'prismatic' : 'revolute',
          object: pivot,
          axis,
          originQuaternion: pivot.quaternion.clone(),
          originPosition: pivot.position.clone(),
          lower: Number.isFinite(range[0]) ? range[0] * (type === 'hinge' ? context.angleScale : 1) : -Math.PI,
          upper: Number.isFinite(range[1]) ? range[1] * (type === 'hinge' ? context.angleScale : 1) : Math.PI,
          value: 0,
        });
      }
    });

    addMjcfMassProperties(element, content, element.getAttribute('name') || 'body');
    await addMjcfGeoms(element, content, bodyClass, defaults, assets, context);
    for (const child of directChildren(element, 'body')) await parseMjcfBody(child, content, bodyClass, defaults, assets, context);
  }

  async function parseMjcf(documentNode, context) {
    const root = documentNode.querySelector('mujoco');
    if (!root) throw new Error('MJCF root element is missing');
    const compiler = directChild(root, 'compiler');
    context.assetDirectory = compiler?.getAttribute('meshdir') || '';
    context.angleScale = String(compiler?.getAttribute('angle') || 'degree').toLowerCase() === 'radian' ? 1 : Math.PI / 180;
    const defaults = parseMjcfDefaults(root);
    const assets = parseMjcfAssets(root);
    const worldbody = directChild(root, 'worldbody');
    if (!worldbody) throw new Error('MJCF worldbody element is missing');
    await addMjcfGeoms(worldbody, state.root, '', defaults, assets, context);
    await Promise.all(directChildren(worldbody, 'body').map((body) => parseMjcfBody(body, state.root, '', defaults, assets, context)));
    return { links: worldbody.querySelectorAll('body').length, format: 'mjcf' };
  }

  function disposeRoot() {
    if (!state) return;
    state.root.traverse((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((item) => item.dispose?.());
      else object.material?.dispose?.();
    });
    state.root.clear();
    state.joints.clear();
    Object.keys(state.roles).forEach((role) => { state.roles[role] = []; });
  }

  function updateCamera() {
    if (!state) return;
    const cosPitch = Math.cos(state.orbit.pitch);
    state.camera.position.set(
      state.orbit.target.x + state.orbit.distance * cosPitch * Math.cos(state.orbit.yaw),
      state.orbit.target.y + state.orbit.distance * cosPitch * Math.sin(state.orbit.yaw),
      state.orbit.target.z + state.orbit.distance * Math.sin(state.orbit.pitch),
    );
    state.camera.lookAt(state.orbit.target);
  }

  function fitView() {
    if (!state || !state.root.children.length) return;
    state.root.updateMatrixWorld(true);
    const bounds = new THREE.Box3();
    const bodyObjects = state.roles.visual.length ? state.roles.visual : state.roles.collision;
    bodyObjects.forEach((object) => bounds.expandByObject(object, true));
    if (bounds.isEmpty()) return;
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const radius = Math.max(size.length() * 0.5, 0.12);
    state.orbit.target.copy(center);
    state.orbit.distance = Math.max(radius / Math.tan(THREE.MathUtils.degToRad(state.camera.fov * 0.5)) * 1.25, 0.35);
    state.orbit.yaw = -Math.PI / 4;
    state.orbit.pitch = Math.PI / 7;
    state.camera.near = Math.max(radius / 1000, 0.001);
    state.camera.far = Math.max(radius * 100, 100);
    state.camera.updateProjectionMatrix();
    state.grid.position.z = bounds.min.z;
    const gridScale = Math.max(radius / 2, 0.1);
    state.grid.scale.setScalar(gridScale);
    state.axes.scale.setScalar(Math.max(radius, 0.2));
    state.roles.jointAxes.forEach((helper) => helper.userData.setRobotScale?.(radius));
    updateCamera();
  }

  function attachControls(canvas) {
    const drag = { active: false, mode: 'orbit', x: 0, y: 0 };
    canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    canvas.addEventListener('pointerdown', (event) => {
      drag.active = true;
      drag.mode = event.button === 2 || event.button === 1 || event.shiftKey ? 'pan' : 'orbit';
      drag.x = event.clientX;
      drag.y = event.clientY;
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!drag.active || !state) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      drag.x = event.clientX;
      drag.y = event.clientY;
      if (drag.mode === 'orbit') {
        state.orbit.yaw -= dx * 0.008;
        state.orbit.pitch = Math.max(-1.48, Math.min(1.48, state.orbit.pitch + dy * 0.008));
      } else {
        const right = new THREE.Vector3().setFromMatrixColumn(state.camera.matrixWorld, 0);
        const up = new THREE.Vector3().setFromMatrixColumn(state.camera.matrixWorld, 1);
        const scale = state.orbit.distance * 0.0015;
        state.orbit.target.addScaledVector(right, -dx * scale).addScaledVector(up, dy * scale);
      }
      updateCamera();
    });
    const stop = () => { drag.active = false; };
    canvas.addEventListener('pointerup', stop);
    canvas.addEventListener('pointercancel', stop);
    canvas.addEventListener('wheel', (event) => {
      if (!state) return;
      event.preventDefault();
      state.orbit.distance = Math.max(0.03, Math.min(500, state.orbit.distance * Math.exp(event.deltaY * 0.001)));
      updateCamera();
    }, { passive: false });
  }

  function createViewer() {
    const stage = document.querySelector('.robot-model-stage, .model-stage');
    if (!stage) throw new Error('Robot viewer stage is unavailable');
    let canvas = document.getElementById('urdfCanvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'urdfCanvas';
      canvas.className = 'urdf-canvas';
      canvas.setAttribute('aria-label', 'Interactive Three.js robot model');
      stage.appendChild(canvas);
    }
    canvas.hidden = false;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0xe8eff4, 1);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if ('outputColorSpace' in renderer) renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.001, 1000);
    camera.up.set(0, 0, 1);
    const root = new THREE.Group();
    root.name = 'robot';
    scene.add(root);
    const hemisphere = new THREE.HemisphereLight(0xffffff, 0xb9c7d0, 2.65);
    scene.add(hemisphere);
    const key = new THREE.DirectionalLight(0xffffff, 3.5);
    key.position.set(3, -4, 6);
    key.castShadow = true;
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xb8dcf5, 1.65);
    fill.position.set(-4, 2, 3);
    scene.add(fill);
    const grid = new THREE.GridHelper(2, 20, 0x7893a4, 0xb8c7d0);
    grid.rotation.x = Math.PI / 2;
    grid.material.transparent = true;
    grid.material.opacity = 0.68;
    scene.add(grid);
    const axes = new THREE.AxesHelper(0.22);
    scene.add(axes);
    const resize = () => {
      const rect = stage.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    state = {
      renderer, scene, camera, root, grid, axes, resize,
      joints: new Map(),
      roles: { visual: [], collision: [], inertial: [], centerOfMass: [], jointAxes: [] },
      visibility: { visual: true, collision: false, inertial: false, centerOfMass: false, grid: true, axes: true, jointAxes: false },
      generation: 0,
      orbit: { target: new THREE.Vector3(), distance: 2, yaw: -Math.PI / 4, pitch: Math.PI / 7 },
    };
    attachControls(canvas);
    new ResizeObserver(resize).observe(stage);
    window.addEventListener('resize', resize);
    resize();
    updateCamera();
    const animate = () => {
      if (!state || state.renderer !== renderer) return;
      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
    return state;
  }

  function jointList() {
    if (!state) return [];
    return Array.from(state.joints.values()).map((joint) => ({
      name: joint.name,
      type: joint.type,
      lower: joint.lower,
      upper: joint.upper,
      value: joint.value,
    }));
  }

  function setJointPositions(positions = {}) {
    if (!state) return;
    Object.entries(positions).forEach(([name, requested]) => {
      const joint = state.joints.get(name);
      if (!joint) return;
      const numeric = Number(requested);
      if (!Number.isFinite(numeric)) return;
      const value = Math.max(joint.lower, Math.min(joint.upper, numeric));
      joint.value = value;
      if (joint.type === 'prismatic') {
        joint.object.position.copy(joint.originPosition).addScaledVector(joint.axis, value);
      } else {
        joint.object.position.copy(joint.originPosition);
        joint.object.quaternion.copy(joint.originQuaternion).multiply(new THREE.Quaternion().setFromAxisAngle(joint.axis, value));
      }
      joint.object.updateMatrixWorld(true);
    });
  }

  function setVisibility(options = {}) {
    if (!state) return;
    ['visual', 'collision', 'inertial', 'centerOfMass', 'jointAxes'].forEach((role) => {
      if (typeof options[role] !== 'boolean') return;
      state.visibility[role] = options[role];
      state.roles[role].forEach((object) => { object.visible = options[role]; });
    });
    // First enable of the collision layer materialises the deferred meshes.
    if (options.collision === true && Array.isArray(state.deferredCollision) && state.deferredCollision.length) {
      state.deferredCollision.splice(0).forEach((task) => { task(); });
    }
    // When the collision shell is shown, dim the opaque visual body so the
    // (usually smaller, internal) collision primitives read through it. Restore
    // full opacity when the shell is hidden. Grid stays untouched.
    if (typeof options.collision === 'boolean') {
      const shellVisible = options.collision;
      state.roles.visual.forEach((object) => {
        if (!object.material || object.userData._baseOpacity == null) {
          object.userData._baseOpacity = object.material?.opacity ?? 1;
        }
        const base = object.userData._baseOpacity;
        object.material.opacity = shellVisible ? Math.min(base, 0.28) : base;
        object.material.transparent = shellVisible || base < 0.999;
        object.material.depthWrite = !shellVisible;
      });
    }
    if (typeof options.grid === 'boolean') {
      state.visibility.grid = options.grid;
      state.grid.visible = options.grid;
    }
    if (typeof options.axes === 'boolean') {
      state.visibility.axes = options.axes;
      state.axes.visible = options.axes;
    }
  }

  async function renderRobotModel(xmlText, options = {}) {
    if (!THREE) THREE = await import(THREE_URL);
    if (!state) createViewer(); else disposeRoot();
    state.generation += 1;
    inertialRecords = [];
    const documentNode = new DOMParser().parseFromString(String(xmlText || ''), 'application/xml');
    if (documentNode.querySelector('parsererror')) throw new Error('Robot XML could not be parsed');
    const format = String(options.format || (documentNode.querySelector('mujoco') ? 'mjcf' : 'urdf')).toLowerCase();
    const context = {
      files: options.files || [],
      filename: options.filename || '',
      baseUrl: options.baseUrl || '',
      assetDirectory: '',
      missingMeshes: 0,
      progressive: true,
      generation: state.generation,
      pendingMeshes: 0,
      loadedMeshes: 0,
      pendingTasks: [],
      deferCollision: !state.visibility.collision,
      deferredCollision: [],
    };
    const summary = format === 'mjcf' ? await parseMjcf(documentNode, context) : await parseUrdf(documentNode, context);
    state.deferredCollision = context.deferredCollision;
    setVisibility(state.visibility);
    fitView();
    const detail = {
      ...summary,
      joints: jointList(),
      visualCount: state.roles.visual.length,
      collisionCount: state.roles.collision.length,
      inertialCount: state.roles.inertial.length,
      centerOfMassCount: state.roles.centerOfMass.length,
      jointAxisCount: state.roles.jointAxes.length,
      missingMeshes: context.missingMeshes,
    };
    window.dispatchEvent(new CustomEvent('robot-viewer-ready', { detail }));
    if (context.pendingTasks.length) {
      Promise.allSettled(context.pendingTasks).then(() => {
        if (state?.generation !== context.generation) return;
        fitView();
        window.dispatchEvent(new CustomEvent('robot-viewer-progress', { detail: { loaded: context.pendingMeshes, total: context.pendingMeshes, complete: true } }));
      });
    }
    return detail;
  }

  window.renderRobotModel = renderRobotModel;
  window.getRobotInertialData = () => inertialRecords.slice();
  window.renderUrdfModel = (xmlText, files, filename, baseUrl) => renderRobotModel(xmlText, { format: 'urdf', files, filename, baseUrl });
  window.setRobotJointPositions = setJointPositions;
  window.setUrdfJointPositions = setJointPositions;
  window.getRobotViewerJoints = jointList;
  window.fitRobotViewer = fitView;
  window.setRobotViewerVisibility = setVisibility;
  window.__debugViewerState = () => state;
}());
