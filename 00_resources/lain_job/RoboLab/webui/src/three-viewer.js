import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import URDFLoader from "urdf-loader";

class RoboThreeViewer {
  constructor(container) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x292d33);
    this.camera = new THREE.PerspectiveCamera(48, 1, 0.001, 1000);
    this.camera.position.set(1.4, 1.1, 1.0);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.autoClear = false;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.style.cssText = "position:absolute;inset:0;width:100%;height:100%;z-index:2";
    container.prepend(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
    this.controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x263445, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3.2);
    key.position.set(3, 4, 5); key.castShadow = true; this.scene.add(key);
    const fill = new THREE.DirectionalLight(0x8cbcff, 1.2);
    fill.position.set(-3, 1, -2); this.scene.add(fill);
    // URDF/MJCF convention is Z-up.  Three.js world space is Y-up.  Keep one
    // explicit conversion root, as robot_viewer does, so robot, joints and
    // local axes share exactly the same transform.  The ground stays in the
    // Three.js world (Y=0) and is therefore never rotated with the robot.
    this.world = new THREE.Group();
    this.world.name = "robolab-urdf-world";
    this.world.rotation.x = -Math.PI / 2;
    this.scene.add(this.world);
    this.grid = new THREE.GridHelper(12, 48, 0x4d5865, 0x343a42);
    this.grid.position.y = 0;
    this.scene.add(this.grid);
    this.setupOrientationGizmo();
    this.axes = [];
    this.inertiaHelpers = [];
    this.visibility = { visual: true, collision: false, axis: false, inertia: false };
    this.loadRevision = 0;
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.animate();
  }

  setupOrientationGizmo() {
    this.gizmoScene = new THREE.Scene();
    this.gizmoCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 10);
    // Leave enough projection padding for labels when an axis points toward
    // the top edge.  The larger render viewport below keeps the gizmo itself
    // legible while preventing the label sprites from being clipped.
    this.gizmoCamera.position.set(0, 0, 3.05);
    this.gizmo = new THREE.AxesHelper(0.72);
    this.gizmoScene.add(this.gizmo);
    this.gizmoViewRotation = new THREE.Matrix4();
    const label = (text, color, position) => {
      const canvas = document.createElement("canvas"); canvas.width = 64; canvas.height = 64;
      const context = canvas.getContext("2d"); context.font = "bold 38px sans-serif"; context.textAlign = "center"; context.textBaseline = "middle"; context.fillStyle = color; context.fillText(text, 32, 32);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthTest: false }));
      sprite.position.copy(position); sprite.scale.setScalar(0.28); this.gizmo.add(sprite);
    };
    label("X", "#ff5555", new THREE.Vector3(0.88, 0, 0));
    label("Y", "#55dd77", new THREE.Vector3(0, 0.88, 0));
    label("Z", "#5599ff", new THREE.Vector3(0, 0, 0.88));
  }

  async load(workspacePath) {
    const revision = ++this.loadRevision;
    if (this.robot) this.world.remove(this.robot);
    this.axes.forEach((axis) => axis.parent?.remove(axis)); this.axes = [];
    this.inertiaHelpers.forEach((helper) => helper.parent?.remove(helper)); this.inertiaHelpers = [];
    const loader = new URDFLoader();
    loader.parseCollision = true;
    loader.packages = "";
    const url = `/workspace/${workspacePath.split("/").map(encodeURIComponent).join("/")}`;
    const robot = await new Promise((resolve, reject) => loader.load(url, resolve, undefined, reject));
    // Ignore an older request that finished after a newer model was selected.
    // Without this guard, a late URDF response could replace the new robot
    // and reintroduce its previous pose.
    if (revision !== this.loadRevision) return null;
    this.robot = robot;
    this.robot.traverse((object) => {
      if (object.isMesh) { object.castShadow = true; object.receiveShadow = true; }
      if (object.isURDFCollider) {
        object.traverse((part) => {
          if (part.isMesh) {
            part.material = new THREE.MeshPhongMaterial({ color: 0xffd84d, transparent: true, opacity: 0.34, wireframe: false, depthWrite: false, side: THREE.DoubleSide });
          }
        });
      }
    });
    Object.values(this.robot.joints || {}).forEach((joint) => {
      if (joint.jointType && !["revolute", "continuous"].includes(joint.jointType)) return;
      const rawAxis = joint.axis;
      const direction = rawAxis?.isVector3 ? rawAxis.clone().normalize() :
        (Array.isArray(rawAxis) ? new THREE.Vector3(...rawAxis).normalize() : new THREE.Vector3(0, 0, 1));
      const axis = new THREE.Group();
      axis.name = `${joint.name}_positive_rotation_axis`;
      const linear = new THREE.ArrowHelper(direction, new THREE.Vector3(0, 0, 0), 0.14, 0xff3030, 0.035, 0.018);
      axis.add(linear);
      // Counter-clockwise circular arrow follows the right-hand rule around
      // the joint axis.  The ring starts in the local XY plane (normal +Z)
      // and is rotated onto the URDF joint axis.
      const ringCenter = direction.clone().multiplyScalar(0.07);
      const rotationRing = new THREE.Group();
      rotationRing.position.copy(ringCenter);
      rotationRing.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
      const arc = new THREE.EllipseCurve(0, 0, 0.045, 0.045, 0, Math.PI * 1.65, false, 0);
      const arcPoints = arc.getPoints(42).map((point) => new THREE.Vector3(point.x, point.y, 0));
      const arcPath = new THREE.CatmullRomCurve3(arcPoints);
      const ring = new THREE.Mesh(
        new THREE.TubeGeometry(arcPath, 42, 0.0012, 6, false),
        new THREE.MeshBasicMaterial({ color: 0x28d17c, transparent: true, opacity: 0.95, depthTest: false })
      );
      rotationRing.add(ring);
      axis.add(rotationRing);
      const tip = new THREE.Mesh(
        new THREE.ConeGeometry(0.0036, 0.009, 8),
        new THREE.MeshBasicMaterial({ color: 0x28d17c, depthTest: false })
      );
      const end = arcPoints.at(-1), beforeEnd = arcPoints.at(-3);
      const tangent = end.clone().sub(beforeEnd).normalize();
      tip.position.copy(end);
      tip.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent);
      rotationRing.add(tip);
      axis.visible = this.visibility.axis; joint.add(axis); this.axes.push(axis);
    });
    this.buildInertiaHelpers(window.robolabInspectionLinks || []);
    this.world.add(this.robot);
    this.applyVisibility();
    this.fit();
    return { joints: Object.keys(this.robot.joints || {}), links: Object.keys(this.robot.links || {}), inertia: this.inertiaHelpers.length, axes: this.axes.length };
  }

  setJoint(name, value, { ignoreLimits = false } = {}) {
    const joint = this.robot?.joints?.[name];
    if (!joint?.setJointValue) return;
    const previousIgnoreLimits = joint.ignoreLimits;
    if (ignoreLimits) joint.ignoreLimits = true;
    joint.setJointValue(Number(value));
    joint.ignoreLimits = previousIgnoreLimits;
  }

  setFov(value = 48) {
    const fov = THREE.MathUtils.clamp(Number(value) || 48, 15, 100);
    this.camera.fov = fov;
    this.camera.updateProjectionMatrix();
    return fov;
  }

  focusLink(name) {
    const link = this.robot?.links?.[name];
    if (!link) return;
    link.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(link);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 0.08);
    const direction = this.camera.position.clone().sub(this.controls.target).normalize();
    this.controls.target.copy(center);
    this.camera.position.copy(center).add(direction.multiplyScalar(radius * 3));
    this.controls.update();
  }

  setUp(up = "+Z") {
    const sign = up.startsWith("+") ? 1 : -1;
    const axis = up.slice(-1).toUpperCase();
    this.world.rotation.set(0, 0, 0);
    if (axis === "X") this.world.rotation.z = sign > 0 ? Math.PI / 2 : -Math.PI / 2;
    else if (axis === "Y") this.world.rotation.x = sign > 0 ? 0 : Math.PI;
    else this.world.rotation.x = sign > 0 ? -Math.PI / 2 : Math.PI / 2;
    this.fit();
  }

  setVisibility(kind, visible) {
    this.visibility[kind] = visible;
    this.applyVisibility();
  }

  buildInertiaHelpers(linkData) {
    const byName = new Map(linkData.map((link) => [link.name, link]));
    Object.values(this.robot.links || {}).forEach((linkObject) => {
      const data = byName.get(linkObject.name);
      if (!data?.inertia || !(data.mass > 0)) return;
      const ixx = Number(data.inertia.ixx || 0), iyy = Number(data.inertia.iyy || 0), izz = Number(data.inertia.izz || 0);
      if (!(ixx > 0 && iyy > 0 && izz > 0)) return;
      const a2 = 6 * (iyy + izz - ixx) / data.mass;
      const b2 = 6 * (ixx + izz - iyy) / data.mass;
      const c2 = 6 * (ixx + iyy - izz) / data.mass;
      if (!(a2 > 1e-10 && b2 > 1e-10 && c2 > 1e-10)) return;
      const geometry = new THREE.BoxGeometry(1, 1, 1);
      const material = new THREE.MeshBasicMaterial({ color: 0x5aa9ff, transparent: true, opacity: 0.34, depthTest: false, depthWrite: false });
      const ellipsoid = new THREE.Mesh(geometry, material);
      const origin = String(data.inertial_origin?.xyz || "0 0 0").trim().split(/\s+/).map(Number);
      const rpy = String(data.inertial_origin?.rpy || "0 0 0").trim().split(/\s+/).map(Number);
      ellipsoid.position.set(origin[0] || 0, origin[1] || 0, origin[2] || 0);
      ellipsoid.rotation.set(rpy[0] || 0, rpy[1] || 0, rpy[2] || 0);
      // Equivalent solid ellipsoid: Ixx=m(b²+c²)/5 and cyclic variants.
      ellipsoid.scale.set(Math.sqrt(a2), Math.sqrt(b2), Math.sqrt(c2));
      ellipsoid.visible = this.visibility.inertia;
      ellipsoid.name = `${linkObject.name}_inertia_ellipsoid`;
      linkObject.add(ellipsoid); this.inertiaHelpers.push(ellipsoid);
    });
  }

  applyVisibility() {
    if (!this.robot) return;
    this.robot.traverse((object) => {
      if (object.isURDFVisual) {
        object.visible = this.visibility.visual;
        object.traverse((part) => {
          if (!part.isMesh || !part.material) return;
          const materials = Array.isArray(part.material) ? part.material : [part.material];
          materials.forEach((material) => {
            if (material.userData.robolabOriginalOpacity === undefined) {
              material.userData.robolabOriginalOpacity = material.opacity;
              material.userData.robolabOriginalTransparent = material.transparent;
              material.userData.robolabOriginalDepthWrite = material.depthWrite;
            }
            if (this.visibility.axis) {
              material.transparent = true;
              material.opacity = Math.min(material.userData.robolabOriginalOpacity, 0.32);
              material.depthWrite = false;
            } else {
              material.opacity = material.userData.robolabOriginalOpacity;
              material.transparent = material.userData.robolabOriginalTransparent;
              material.depthWrite = material.userData.robolabOriginalDepthWrite;
            }
            material.needsUpdate = true;
          });
        });
      }
      if (object.isURDFCollider) object.visible = this.visibility.collision;
    });
    this.axes.forEach((axis) => { axis.visible = this.visibility.axis; });
    this.inertiaHelpers.forEach((helper) => { helper.visible = this.visibility.inertia; });
  }

  fit() {
    if (!this.robot) return;
    this.world.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(this.robot);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 0.2);
    this.grid.position.y = box.min.y - radius * 0.002;
    this.controls.target.copy(center);
    this.camera.position.copy(center).add(new THREE.Vector3(radius * 1.5, radius * 1.15, radius * 1.5));
    this.camera.near = Math.max(radius / 1000, 0.001); this.camera.far = radius * 100; this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  resize() {
    const width = Math.max(this.container.clientWidth, 1), height = Math.max(this.container.clientHeight, 1);
    this.renderer.setSize(width, height, false); this.camera.aspect = width / height; this.camera.updateProjectionMatrix();
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    this.controls.update();
    this.renderer.setScissorTest(false);
    this.renderer.clear(true, true, true);
    this.renderer.setViewport(0, 0, this.renderer.domElement.width, this.renderer.domElement.height);
    this.renderer.render(this.scene, this.camera);
    const size = Math.round(112 * Math.min(window.devicePixelRatio, 2));
    const margin = Math.round(15 * Math.min(window.devicePixelRatio, 2));
    // Use the exact same model-view rotation as the main scene.  This keeps
    // the gizmo aligned with the URDF world frame (including the Z-up root
    // conversion) for every orbit angle, instead of relying on Euler order or
    // a separately reconstructed camera quaternion.
    this.camera.updateMatrixWorld(true);
    this.world.updateMatrixWorld(true);
    this.gizmoViewRotation.multiplyMatrices(this.camera.matrixWorldInverse, this.world.matrixWorld);
    // Both inputs are rigid transforms, so the product already has a pure
    // rotation block (plus translation, which setFromRotationMatrix ignores).
    this.gizmo.quaternion.setFromRotationMatrix(this.gizmoViewRotation);
    this.renderer.clearDepth();
    this.renderer.setScissorTest(true);
    this.renderer.setScissor(margin, margin, size, size);
    this.renderer.setViewport(margin, margin, size, size);
    this.renderer.render(this.gizmoScene, this.gizmoCamera);
    this.renderer.setScissorTest(false);
  }
}

window.RoboThreeViewer = RoboThreeViewer;
window.dispatchEvent(new Event("robolab-viewer-ready"));
