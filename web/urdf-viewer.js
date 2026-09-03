/* Lightweight Three.js URDF preview used by the validation workbench. */
(function () {
  let THREE = null;
  let state = null;

  function parseVector(value, fallback = [0, 0, 0]) {
    const values = String(value || '').trim().split(/\s+/).map(Number);
    return values.length >= 3 && values.every(Number.isFinite) ? values.slice(0, 3) : fallback;
  }

  function material(color) {
    return new THREE.MeshStandardMaterial({ color: color || 0x8ab4ff, roughness: 0.72, metalness: 0.08 });
  }

  function geometry(node) {
    const mesh = node.querySelector(':scope > mesh');
    const box = node.querySelector(':scope > box');
    const sphere = node.querySelector(':scope > sphere');
    const cylinder = node.querySelector(':scope > cylinder');
    if (box) {
      const size = parseVector(box.getAttribute('size'), [0.1, 0.1, 0.1]);
      return new THREE.BoxGeometry(Math.max(size[0], 0.001), Math.max(size[1], 0.001), Math.max(size[2], 0.001));
    }
    if (sphere) return new THREE.SphereGeometry(Math.max(Number(sphere.getAttribute('radius')) || 0.05, 0.001), 20, 12);
    if (cylinder) {
      const radius = Math.max(Number(cylinder.getAttribute('radius')) || 0.04, 0.001);
      const length = Math.max(Number(cylinder.getAttribute('length')) || 0.1, 0.001);
      const result = new THREE.CylinderGeometry(radius, radius, length, 20);
      result.rotateX(Math.PI / 2);
      return result;
    }
    // Mesh resources are validated and persisted by the backend. The compact
    // viewer deliberately uses a link marker when a loader is unavailable.
    if (mesh) return new THREE.BoxGeometry(0.12, 0.12, 0.12);
    return new THREE.BoxGeometry(0.08, 0.08, 0.08);
  }

  function parseObj(text) {
    const vertices = [], faces = [];
    String(text).split(/\r?\n/).forEach((line) => {
      const parts = line.trim().split(/\s+/);
      if (parts[0] === 'v' && parts.length >= 4) vertices.push(parts.slice(1, 4).map(Number));
      if (parts[0] === 'f' && parts.length >= 4) faces.push(parts.slice(1).map((token) => Number(token.split('/')[0]) - 1));
    });
    const positions = [];
    faces.forEach((face) => { for (let i = 1; i < face.length - 1; i += 1) [face[0], face[i], face[i + 1]].forEach((index) => positions.push(...(vertices[index] || [0, 0, 0]))); });
    const result = new THREE.BufferGeometry(); result.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); result.computeVertexNormals(); return result;
  }

  function parseStl(buffer) {
    const view = new DataView(buffer); const binary = buffer.byteLength >= 84 && view.getUint32(80, true) * 50 + 84 === buffer.byteLength;
    const positions = [];
    if (binary) { const count = view.getUint32(80, true); for (let i = 0; i < count; i += 1) { const base = 84 + i * 50 + 12; for (let j = 0; j < 3; j += 1) for (let k = 0; k < 3; k += 1) positions.push(view.getFloat32(base + j * 12 + k * 4, true)); } }
    else { const text = new TextDecoder().decode(buffer); const matches = [...text.matchAll(/vertex\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)/gi)]; matches.forEach((match) => positions.push(Number(match[1]), Number(match[2]), Number(match[3]))); }
    const result = new THREE.BufferGeometry(); result.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); result.computeVertexNormals(); return result;
  }

  async function meshGeometry(filename, files) {
    const normalized = String(filename || '').replace(/^[./]+/, '').toLowerCase();
    const file = (files || []).find((item) => String(item.webkitRelativePath || item.name).replace(/^[./]+/, '').toLowerCase().endsWith(normalized) || String(item.name).toLowerCase() === normalized.split('/').pop());
    if (!file) return null;
    const ext = normalized.split('.').pop();
    if (ext === 'obj') return parseObj(await file.text());
    if (ext === 'stl') return parseStl(await file.arrayBuffer());
    return null;
  }

  function origin(node) {
    const item = node.querySelector(':scope > origin');
    if (!item) return { xyz: [0, 0, 0], rpy: [0, 0, 0] };
    return { xyz: parseVector(item.getAttribute('xyz')), rpy: parseVector(item.getAttribute('rpy')) };
  }

  function createViewer() {
    const stage = document.querySelector('.model-stage');
    if (!stage) return null;
    let canvas = document.querySelector('#urdfCanvas');
    if (!canvas) { canvas = document.createElement('canvas'); canvas.id = 'urdfCanvas'; canvas.className = 'urdf-canvas'; stage.appendChild(canvas); }
    canvas.hidden = false;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x0c1114, 1);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xe8f3ff, 0x26323b, 2.0));
    const key = new THREE.DirectionalLight(0xffffff, 2.3); key.position.set(3, 4, 5); scene.add(key);
    scene.add(new THREE.GridHelper(4, 20, 0x59727e, 0x26353d));
    scene.add(new THREE.AxesHelper(0.5));
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100); camera.position.set(2.2, 1.6, 2.4);
    const root = new THREE.Group(); scene.add(root);
    const resize = () => { const rect = stage.getBoundingClientRect(); renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false); camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height); camera.updateProjectionMatrix(); };
    let dragging = false, lastX = 0, lastY = 0;
    canvas.addEventListener('pointerdown', (event) => { dragging = true; lastX = event.clientX; lastY = event.clientY; canvas.setPointerCapture(event.pointerId); });
    canvas.addEventListener('pointermove', (event) => { if (!dragging) return; root.rotation.y += (event.clientX - lastX) * 0.01; root.rotation.x += (event.clientY - lastY) * 0.01; lastX = event.clientX; lastY = event.clientY; });
    canvas.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', (event) => { camera.position.multiplyScalar(event.deltaY > 0 ? 1.08 : 0.93); camera.position.clampLength(0.25, 30); });
    window.addEventListener('resize', resize); resize();
    const animate = () => { if (!state || state.renderer !== renderer) return; renderer.render(scene, camera); requestAnimationFrame(animate); }; requestAnimationFrame(animate);
    return { renderer, scene, camera, root, resize };
  }

  async function renderUrdfModel(xmlText, files = []) {
    if (!THREE) THREE = await import('/web/sim2sim/vendor/three/build/three.module.js');
    if (state?.root) state.root.clear(); else state = createViewer();
    if (!state) throw new Error('model viewer stage is unavailable');
    const xml = new DOMParser().parseFromString(xmlText, 'application/xml');
    if (xml.querySelector('parsererror')) throw new Error('URDF XML parse failed');
    const links = [...xml.querySelectorAll('robot > link')];
    const joints = [...xml.querySelectorAll('robot > joint')];
    const groups = new Map(links.map((link) => [link.getAttribute('name'), new THREE.Group()]));
    await Promise.all(links.map(async (link) => {
      const group = groups.get(link.getAttribute('name')); group.userData.link = link.getAttribute('name');
      const visual = link.querySelector(':scope > visual');
      const node = visual?.querySelector(':scope > geometry');
      const meshNode = node?.querySelector(':scope > mesh');
      const meshPath = meshNode?.getAttribute('filename') || meshNode?.getAttribute('url') || '';
      const color = visual?.querySelector(':scope > material > color')?.getAttribute('rgba')?.split(/\s+/).slice(0, 3).map((v) => Number(v) * 255).reduce((a, v, i) => a + (v << (16 - i * 8)), 0) || 0x8ab4ff;
      const mesh = new THREE.Mesh((await meshGeometry(meshPath, files)) || geometry(node || link), material(color));
      const pose = origin(visual || link); mesh.position.set(...pose.xyz); mesh.rotation.set(...pose.rpy); group.add(mesh);
    }));
    const childLinks = new Set();
    joints.forEach((joint) => {
      const parent = groups.get(joint.querySelector(':scope > parent')?.getAttribute('link'));
      const childName = joint.querySelector(':scope > child')?.getAttribute('link');
      const child = groups.get(childName); if (!child) return;
      childLinks.add(childName); parent?.add(child);
      const pose = origin(joint); child.position.add(new THREE.Vector3(...pose.xyz)); child.rotation.set(...pose.rpy);
    });
    groups.forEach((group, name) => { if (!childLinks.has(name)) state.root.add(group); });
    const bounds = new THREE.Box3().setFromObject(state.root); const center = bounds.getCenter(new THREE.Vector3()); const size = bounds.getSize(new THREE.Vector3());
    state.root.position.sub(center); const radius = Math.max(size.length() * 0.65, 0.4); state.camera.position.set(radius, radius * 0.65, radius); state.camera.lookAt(0, 0, 0); state.resize();
    return { links: links.length, joints: joints.length };
  }
  window.renderUrdfModel = renderUrdfModel;
}());
