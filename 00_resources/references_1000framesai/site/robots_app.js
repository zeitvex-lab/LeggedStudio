import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { robots, ApiError } from "../shared/api.js";

const LEGS = ["fl", "fr", "rl", "rr"];
const QUADRUPED_MORPHOLOGY = "quadruped_12dof";
const WHEEL_LEG_MORPHOLOGY = "wheel_leg_16dof_v1";
const MORPHOLOGY_SEGMENTS = {
  [QUADRUPED_MORPHOLOGY]: ["hip", "thigh", "calf"],
  quadruped_12dof_v1: ["hip", "thigh", "calf"],
  [WHEEL_LEG_MORPHOLOGY]: ["hip", "thigh", "calf", "wheel"],
};

const LEG_LABEL = { fl: "前左 FL", fr: "前右 FR", rl: "后左 RL", rr: "后右 RR" };
const SEG_RANGE = { hip: [-1.5, 1.5], thigh: [-3.0, 3.0], calf: [-2.8, 2.8], wheel: [-6.28, 6.28] };
const CAD_MESH_EXTS = new Set([".stp", ".step", ".stl", ".dae", ".obj"]);
const CAD_UNIT_SCALE = { m: 1, cm: 0.01, mm: 0.001 };
const STEP_TEMPLATE_LABELS = { quadruped_12dof: "四足 12DoF 模板" };
const LINK_ORDER = [
  "base_link",
  "fl_hip_link", "fl_thigh_link", "fl_calf_link", "fl_foot_link",
  "fr_hip_link", "fr_thigh_link", "fr_calf_link", "fr_foot_link",
  "rl_hip_link", "rl_thigh_link", "rl_calf_link", "rl_foot_link",
  "rr_hip_link", "rr_thigh_link", "rr_calf_link", "rr_foot_link",
];
const LINK_COLORS = {
  base_link: 0x38bdf8,
  fl_hip_link: 0x5eead4, fl_thigh_link: 0x2dd4bf, fl_calf_link: 0x14b8a6, fl_foot_link: 0x0f766e,
  fr_hip_link: 0xfbbf24, fr_thigh_link: 0xf59e0b, fr_calf_link: 0xd97706, fr_foot_link: 0x92400e,
  rl_hip_link: 0xa78bfa, rl_thigh_link: 0x8b5cf6, rl_calf_link: 0x7c3aed, rl_foot_link: 0x5b21b6,
  rr_hip_link: 0xfb7185, rr_thigh_link: 0xf43f5e, rr_calf_link: 0xe11d48, rr_foot_link: 0x9f1239,
};

const el = {
  robotList: document.getElementById("robotList"),
  robotCount: document.getElementById("robotCount"),
  deduplicateRobots: document.getElementById("deduplicateRobots"),
  editorTitle: document.getElementById("editorTitle"),
  editorSub: document.getElementById("editorSub"),
  editorStatus: document.getElementById("editorStatus"),
  form: document.getElementById("robotForm"),
  fName: document.getElementById("fName"),
  fVendor: document.getElementById("fVendor"),
  jointOrderTable: document.getElementById("jointOrderTable"),
  jointOrderStatus: document.getElementById("jointOrderStatus"),
  autoMapJoints: document.getElementById("autoMapJoints"),
  orderMapJoints: document.getElementById("orderMapJoints"),
  clearMapJoints: document.getElementById("clearMapJoints"),
  jointAngles: document.getElementById("jointAngles"),
  kpHip: document.getElementById("kpHip"),
  kpThigh: document.getElementById("kpThigh"),
  kpCalf: document.getElementById("kpCalf"),
  kpWheel: document.getElementById("kpWheel"),
  kdHip: document.getElementById("kdHip"),
  kdThigh: document.getElementById("kdThigh"),
  kdCalf: document.getElementById("kdCalf"),
  kdWheel: document.getElementById("kdWheel"),
  controlGainGrid: document.getElementById("controlGainGrid"),
  actionScale: document.getElementById("actionScale"),
  decimation: document.getElementById("decimation"),
  baseHeightTarget: document.getElementById("baseHeightTarget"),
  envelopeHip: document.getElementById("envelopeHip"),
  envelopeThigh: document.getElementById("envelopeThigh"),
  envelopeCalf: document.getElementById("envelopeCalf"),
  envelopeWheel: document.getElementById("envelopeWheel"),
  formError: document.getElementById("formError"),
  saveButton: document.getElementById("saveButton"),
  reloadButton: document.getElementById("reloadButton"),
  saveHint: document.getElementById("saveHint"),
  resetStandingPose: document.getElementById("resetStandingPose"),
  assemblyActiveLink: document.getElementById("assemblyActiveLink"),
  assemblySelection: document.getElementById("assemblySelection"),
  assignSelectedPart: document.getElementById("assignSelectedPart"),
  unassignSelectedPart: document.getElementById("unassignSelectedPart"),
  focusSelectedPart: document.getElementById("focusSelectedPart"),
  transformTranslate: document.getElementById("transformTranslate"),
  transformRotate: document.getElementById("transformRotate"),
  transformSpace: document.getElementById("transformSpace"),
  assemblyViewer: document.getElementById("assemblyViewer"),
  assemblyViewerLabel: document.getElementById("assemblyViewerLabel"),
  urdfUploadForm: document.getElementById("urdfUploadForm"),
  urdfUploadStatus: document.getElementById("urdfUploadStatus"),
  urdfDropZone: document.getElementById("urdfDropZone"),
  urdfFolderInput: document.getElementById("urdfFolderInput"),
  urdfUploadFile: document.getElementById("urdfUploadFile"),
  urdfUploadFileName: document.getElementById("urdfUploadFileName"),
  urdfRobotName: document.getElementById("urdfRobotName"),
  urdfVendor: document.getElementById("urdfVendor"),
  urdfMorphology: document.getElementById("urdfMorphology"),
  urdfCreateRobot: document.getElementById("urdfCreateRobot"),
  urdfSimplifyMeshes: document.getElementById("urdfSimplifyMeshes"),
  urdfUploadButton: document.getElementById("urdfUploadButton"),
  urdfUploadError: document.getElementById("urdfUploadError"),
  urdfUploadResult: document.getElementById("urdfUploadResult"),
  urdfMeshStatus: document.getElementById("urdfMeshStatus"),
  expandUrdfViewer: document.getElementById("expandUrdfViewer"),
  stanceResetButton: null,
  stancePoseViewer: document.getElementById("stancePoseViewer"),
  // 全屏模态层
  urdfModal: document.getElementById("urdfModal"),
  urdfModalCanvas: document.getElementById("urdfModalCanvas"),
  urdfModalTitle: document.getElementById("urdfModalTitle"),
  urdfModalMeshStatus: document.getElementById("urdfModalMeshStatus"),
  urdfModalJoints: document.getElementById("urdfModalJoints"),
  urdfModalSave: document.getElementById("urdfModalSave"),
  urdfModalReset: document.getElementById("urdfModalReset"),
  urdfModalClose: document.getElementById("urdfModalClose"),
};

let state = {
  list: [],
  selectedId: null,
  current: null,
  stepJoints: [],
  parts: [],
  solids: [],
  inputMode: "assembly",
  currentAssemblyId: "",
  partObjects: new Map(),
  meshCache: new Map(),
  selectedPartId: "",
  currentAssemblyLink: "base_link",
  transformMode: "translate",
  transformSpace: "local",
  axesVisible: true,
  stanceTemplate: "sa",
  // Pending folder upload files collected from drag-drop
  urdfFolderFiles: null,    // Array<{file, relPath}> | null
  urdfFolderMode: false,    // true when folder drag-drop is staged
};

function segmentsForMorphology(morphology) {
  return MORPHOLOGY_SEGMENTS[String(morphology || QUADRUPED_MORPHOLOGY).toLowerCase()]
    || MORPHOLOGY_SEGMENTS[QUADRUPED_MORPHOLOGY];
}

function canonicalJointsForMorphology(morphology) {
  return LEGS.flatMap((leg) => segmentsForMorphology(morphology).map((segment) => `${leg}_${segment}_joint`));
}

function activeSegments() {
  return segmentsForMorphology(state.current?.morphology);
}

function activeCanonicalJoints() {
  return canonicalJointsForMorphology(state.current?.morphology);
}

function isWheelLegMorphology(morphology = state.current?.morphology) {
  return String(morphology || "").toLowerCase() === WHEEL_LEG_MORPHOLOGY;
}

function setWheelControlVisibility(visible) {
  el.form?.querySelectorAll("[data-wheel-control]").forEach((node) => {
    node.hidden = !visible;
    if (node.matches("input, select, textarea, button")) node.disabled = !visible;
    node.querySelectorAll?.("input, select, textarea, button").forEach((control) => {
      control.disabled = !visible;
    });
  });
  if (el.controlGainGrid) {
    el.controlGainGrid.style.gridTemplateColumns = `46px repeat(${visible ? 4 : 3}, minmax(0, 1fr))`;
  }
}

const viewer = {  renderer: null,
  scene: null,
  camera: null,
  controls: null,
  partGroup: null,
  jointGroup: null,
  transform: null,
  raycaster: new THREE.Raycaster(),
  pointer: new THREE.Vector2(),
  isTransformDragging: false,
  ignoreNextPick: false,
  axes: null,
  ro: null,
};

// ── Stance Pose 3D Viewer ─────────────────────────────────────────────────────
const stancePose = {
  renderer: null,
  scene: null,
  camera: null,
  controls: null,
  legJoints: null, // { fl, fr, rl, rr } → { hipGroup, thighGroup, calfGroup } (schematic)
  ro: null,
  // URDF real-mesh kinematic chain
  urdfChain: null,   // null | { root: THREE.Group, jointMap: Map<name,{group,axis,type}>, schematicGroup: THREE.Group }
  schematicGroup: null,  // container for schematic geometry (hidden when URDF chain loaded)
};

// Schematic quadruped proportions (GO2-like, meters)
const STANCE_BODY = { hx: 0.19, hy: 0.065, hz: 0.05 };
const STANCE_HIP_ORIGINS = {
  fl: [0.183, 0.047, 0], fr: [0.183, -0.047, 0],
  rl: [-0.183, 0.047, 0], rr: [-0.183, -0.047, 0],
};
const STANCE_SIDE = { fl: 1, fr: -1, rl: 1, rr: -1 };
const STANCE_HIP_LEN = 0.08;
const STANCE_THIGH_LEN = 0.213;
const STANCE_CALF_LEN = 0.213;
const STANCE_LEG_COLORS = { fl: 0x2dd4bf, fr: 0xfbbf24, rl: 0xa78bfa, rr: 0xfb7185 };

function initStancePoseViewer() {
  const container = el.stancePoseViewer;
  if (!container || stancePose.renderer) return;

  stancePose.scene = new THREE.Scene();
  stancePose.scene.background = new THREE.Color(0x070d14);

  stancePose.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 20);
  stancePose.camera.up.set(0, 0, 1);
  stancePose.camera.position.set(0.65, -0.90, 0.52);

  stancePose.renderer = new THREE.WebGLRenderer({ antialias: true });
  stancePose.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  stancePose.renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.insertBefore(stancePose.renderer.domElement, container.firstChild);

  stancePose.controls = new OrbitControls(stancePose.camera, stancePose.renderer.domElement);
  stancePose.controls.target.set(0, 0, 0.05);
  stancePose.controls.enableDamping = true;
  stancePose.controls.dampingFactor = 0.1;

  stancePose.scene.add(new THREE.HemisphereLight(0xdbeafe, 0x0f172a, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(1, -2, 3);
  stancePose.scene.add(key);

  const grid = new THREE.GridHelper(0.82, 8, 0x1e3040, 0x0f1e28);
  grid.rotation.x = Math.PI / 2;
  stancePose.scene.add(grid);

  buildStanceRobotGeometry();

  stancePose.ro = new ResizeObserver(() => resizeStancePose());
  stancePose.ro.observe(container);
  resizeStancePose();
  animateStancePose();
}

function resizeStancePose() {
  // Route to whichever container currently holds the canvas
  const inModal = el.urdfModal && el.urdfModal.style.display !== "none";
  resizeStancePoseToContainer(inModal ? el.urdfModalCanvas : el.stancePoseViewer);
}

function animateStancePose() {
  requestAnimationFrame(animateStancePose);
  stancePose.controls?.update();
  // 每帧自动追踪容器尺寸——解决 canvas 搬到模态后 resize 时机问题
  if (stancePose.renderer) {
    const canvas = stancePose.renderer.domElement;
    const parent = canvas.parentElement;
    if (parent) {
      const pw = Math.max(1, Math.round(parent.clientWidth  || parent.offsetWidth  || 1));
      const ph = Math.max(1, Math.round(parent.clientHeight || parent.offsetHeight || 1));
      const cur = stancePose.renderer.getSize(new THREE.Vector2());
      if (Math.abs(cur.x - pw) > 2 || Math.abs(cur.y - ph) > 2) {
        stancePose.renderer.setSize(pw, ph, false);
        if (stancePose.camera) {
          stancePose.camera.aspect = pw / ph;
          stancePose.camera.updateProjectionMatrix();
        }
      }
    }
  }
  stancePose.renderer?.render(stancePose.scene, stancePose.camera);
}

function buildStanceRobotGeometry() {
  // All schematic geometry lives inside a single group so it can be hidden
  // when a real URDF kinematic chain is loaded.
  const container = new THREE.Group();
  stancePose.schematicGroup = container;
  stancePose.scene.add(container);

  const { hx, hy, hz } = STANCE_BODY;
  container.add(new THREE.Mesh(
    new THREE.BoxGeometry(hx * 2, hy * 2, hz * 2),
    new THREE.MeshStandardMaterial({ color: 0x38bdf8, roughness: 0.42, metalness: 0.18 }),
  ));

  stancePose.legJoints = {};
  for (const leg of LEGS) {
    const origin = STANCE_HIP_ORIGINS[leg];
    const side = STANCE_SIDE[leg];
    const color = STANCE_LEG_COLORS[leg];
    const segMat = (op = 1) => new THREE.MeshStandardMaterial({ color, roughness: 0.44, metalness: 0.18, transparent: op < 1, opacity: op });

    // Hip group — at body hip origin, rotation.x = hip abduction angle (×side for mirroring)
    const hipGroup = new THREE.Group();
    hipGroup.position.set(...origin);
    container.add(hipGroup);

    // Abad link: cylinder from hip pivot outward along ±Y
    const hipCyl = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, STANCE_HIP_LEN, 12), segMat());
    hipCyl.rotation.z = Math.PI / 2;
    hipCyl.position.set(0, STANCE_HIP_LEN * side / 2, 0);
    hipGroup.add(hipCyl);

    // Thigh group — at end of abad link, rotation.y = thigh swing angle
    const thighGroup = new THREE.Group();
    thighGroup.position.set(0, STANCE_HIP_LEN * side, 0);
    hipGroup.add(thighGroup);

    // Thigh link: cylinder along -Z
    const thighCyl = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.014, STANCE_THIGH_LEN, 12), segMat());
    thighCyl.rotation.x = Math.PI / 2;
    thighCyl.position.set(0, 0, -STANCE_THIGH_LEN / 2);
    thighGroup.add(thighCyl);

    // Calf group — at end of thigh, rotation.y = calf/knee angle
    const calfGroup = new THREE.Group();
    calfGroup.position.set(0, 0, -STANCE_THIGH_LEN);
    thighGroup.add(calfGroup);

    // Calf link: cylinder along -Z
    const calfCyl = new THREE.Mesh(new THREE.CylinderGeometry(0.013, 0.011, STANCE_CALF_LEN, 12), segMat(0.88));
    calfCyl.rotation.x = Math.PI / 2;
    calfCyl.position.set(0, 0, -STANCE_CALF_LEN / 2);
    calfGroup.add(calfCyl);

    // Foot sphere
    const footSphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.024, 14, 10),
      new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.65, metalness: 0 }),
    );
    footSphere.position.set(0, 0, -STANCE_CALF_LEN);
    calfGroup.add(footSphere);

    // Pivot dots at knee and calf joints
    const dotMat = new THREE.MeshBasicMaterial({ color: 0x1e293b });
    for (const g of [thighGroup, calfGroup]) {
      g.add(new THREE.Mesh(new THREE.SphereGeometry(0.011, 8, 6), dotMat));
    }

    stancePose.legJoints[leg] = { hipGroup, thighGroup, calfGroup };
  }
}

function updateStancePoseAngles(angles) {
  const low = {};
  for (const [k, v] of Object.entries(angles || {})) low[String(k).toLowerCase()] = Number(v) || 0;

  // Update real URDF kinematic chain when available.
  if (stancePose.urdfChain) {
    // Re-key canonical slots (fl_hip_joint …) to the robot's REAL URDF joint
    // names via the saved mapping, so sliders drive the correct joints even
    // when the URDF names differ (ABAD/HIP/KNEE). Same fix as _applyModalAngles.
    const mapping = activeJointMapping();
    const remapped = {};
    for (const [slot, val] of Object.entries(low)) {
      const realName = (mapping[slot] || canonicalToUrdf(slot) || slot);
      remapped[String(realName).toLowerCase()] = val;
    }
    updateUrdfChainAngles(stancePose.urdfChain, remapped);
    return;
  }

  // Fall back to schematic.
  if (!stancePose.legJoints) return;
  for (const leg of LEGS) {
    const j = stancePose.legJoints[leg];
    if (!j) continue;
    // Hip abduction: X axis; sign flipped for right-side legs
    j.hipGroup.rotation.x = (low[`${leg}_hip_joint`] || 0) * STANCE_SIDE[leg];
    j.thighGroup.rotation.y = low[`${leg}_thigh_joint`] || 0;
    j.calfGroup.rotation.y = low[`${leg}_calf_joint`] || 0;
  }
}

function collectCurrentStanceAngles() {
  const angles = {};
  el.jointAngles.querySelectorAll('[data-role="num"]').forEach((input) => {
    angles[input.dataset.slot] = num(input.value, 0);
  });
  return angles;
}

init();

async function init() {
  bindEvents();
  await loadList();
  const wanted = new URLSearchParams(location.search).get("robot");
  const pick = state.list.find((r) => r.id === wanted) || state.list[0];
  if (pick) selectRobot(pick.id);
}

function bindEvents() {
  el.form.addEventListener("submit", onSave);
  el.reloadButton.addEventListener("click", () => state.selectedId && selectRobot(state.selectedId));
  el.deduplicateRobots?.addEventListener("click", onDeduplicateRobots);
  el.assemblyActiveLink?.addEventListener("change", () => {
    state.currentAssemblyLink = el.assemblyActiveLink.value || "base_link";
    updateAssemblySelectionPanel();
  });
  el.assignSelectedPart?.addEventListener("click", assignSelectedPartToLink);
  el.unassignSelectedPart?.addEventListener("click", unassignSelectedPart);
  el.focusSelectedPart?.addEventListener("click", () => focusSelectedPart());
  el.transformTranslate?.addEventListener("click", () => setTransformMode("translate"));
  el.transformRotate?.addEventListener("click", () => setTransformMode("rotate"));
  el.transformSpace?.addEventListener("change", () => setTransformSpace(el.transformSpace.value));
  el.urdfUploadForm.addEventListener("submit", onUrdfUpload);
  el.urdfUploadFile.addEventListener("change", onUrdfFilePicked);
  el.urdfFolderInput?.addEventListener("change", onUrdfFolderInputPicked);
  // Drop-zone: folder drag-drop + click to open picker
  if (el.urdfDropZone) {
    el.urdfDropZone.addEventListener("click", onUrdfDropZoneClick);
    el.urdfDropZone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") onUrdfDropZoneClick(); });
    el.urdfDropZone.addEventListener("dragover", (e) => { e.preventDefault(); el.urdfDropZone.classList.add("drag-over"); });
    el.urdfDropZone.addEventListener("dragleave", () => el.urdfDropZone.classList.remove("drag-over"));
    el.urdfDropZone.addEventListener("drop", onUrdfDrop);
  }
  // Live stance pose preview — any slider / number input fires this
  el.jointAngles.addEventListener("input", () => {
    updateStancePoseAngles(collectCurrentStanceAngles());
  });
  el.autoMapJoints.addEventListener("click", () => applyJointMapping("name"));
  el.orderMapJoints.addEventListener("click", () => applyJointMapping("order"));
  el.clearMapJoints.addEventListener("click", () => applyJointMapping("clear"));
  el.resetStandingPose?.addEventListener("click", resetStandingPose);
  // 展开大屏预览
  el.expandUrdfViewer?.addEventListener("click", () => openUrdfModal(state.current));
  // 模态层控制
  el.urdfModalClose?.addEventListener("click", closeUrdfModal);
  el.urdfModalSave?.addEventListener("click", saveUrdfModalPose);
  el.urdfModalReset?.addEventListener("click", resetUrdfModalPose);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeUrdfModal(); });
}

function setupAssemblyViewer() {
  viewer.scene = new THREE.Scene();
  viewer.scene.background = new THREE.Color(0x070d14);
  viewer.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
  viewer.camera.position.set(1.2, -1.5, 0.9);
  viewer.renderer = new THREE.WebGLRenderer({ antialias: true });
  viewer.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  viewer.renderer.outputColorSpace = THREE.SRGBColorSpace;
  el.assemblyViewer.append(viewer.renderer.domElement);

  viewer.controls = new OrbitControls(viewer.camera, viewer.renderer.domElement);
  viewer.controls.enableDamping = true;
  viewer.controls.target.set(0, 0, 0);

  viewer.transform = new TransformControls(viewer.camera, viewer.renderer.domElement);
  viewer.transform.setMode(state.transformMode);
  viewer.transform.setSpace(state.transformSpace);
  viewer.transform.addEventListener("dragging-changed", (event) => {
    viewer.isTransformDragging = Boolean(event.value);
    viewer.controls.enabled = !event.value;
    if (!event.value) {
      viewer.ignoreNextPick = true;
      window.setTimeout(() => { viewer.ignoreNextPick = false; }, 160);
    }
  });
  viewer.transform.addEventListener("objectChange", onTransformObjectChange);

  const ambient = new THREE.HemisphereLight(0xdbeafe, 0x0f172a, 1.6);
  viewer.scene.add(ambient);
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(2, -3, 4);
  viewer.scene.add(key);

  const grid = new THREE.GridHelper(2.2, 22, 0x334155, 0x172033);
  grid.rotation.x = Math.PI / 2;
  viewer.scene.add(grid);
  viewer.axes = new THREE.AxesHelper(0.35);
  viewer.scene.add(viewer.axes);
  viewer.previewGroup = new THREE.Group();
  viewer.partGroup = new THREE.Group();
  viewer.jointGroup = new THREE.Group();
  viewer.scene.add(viewer.previewGroup, viewer.partGroup, viewer.jointGroup, viewer.transform);
  viewer.renderer.domElement.addEventListener("click", onViewerPointerDown);

  viewer.ro = new ResizeObserver(resizeViewer);
  viewer.ro.observe(el.assemblyViewer);
  resizeViewer();
  animateViewer();
}

function resizeViewer() {
  if (!viewer.renderer || !viewer.camera) return;
  const rect = el.assemblyViewer.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  viewer.renderer.setSize(width, height, false);
  viewer.camera.aspect = width / height;
  viewer.camera.updateProjectionMatrix();
}

function animateViewer() {
  requestAnimationFrame(animateViewer);
  viewer.controls?.update();
  viewer.renderer?.render(viewer.scene, viewer.camera);
}

function clearGroup(group) {
  if (!group) return;
  while (group.children.length) {
    const child = group.children.pop();
    child?.traverse?.((node) => {
      node.geometry?.dispose?.();
      if (Array.isArray(node.material)) node.material.forEach((m) => m.dispose?.());
      else node.material?.dispose?.();
    });
  }
}

async function loadAssemblyPreviewGeometry() {
  if (state.assemblyPreviewGeometry) return state.assemblyPreviewGeometry.clone();
  const url = resolveAssemblyPreviewUrl();
  if (!url) return null;
  if (!state.assemblyPreviewPromise) {
    state.assemblyPreviewPromise = (async () => {
      const res = await fetch(url, {
        method: "GET",
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(formatPreviewError(res.status, text));
      }
      const buffer = await res.arrayBuffer();
      const geometry = parseStlGeometry(buffer);
      normalizePreviewGeometryKeepPose(geometry, state.assemblyPreviewScale || 1);
      state.assemblyPreviewGeometry = geometry.clone();
      return geometry;
    })().catch((err) => {
      state.assemblyPreviewPromise = null;
      throw err;
    });
  }
  const geometry = await state.assemblyPreviewPromise;
  return geometry.clone();
}

function buildDefaultStepJoints() {
  const rows = [];
  const geom = {
    fl: [0.20, 0.10, 1],
    fr: [0.20, -0.10, -1],
    rl: [-0.20, 0.10, 1],
    rr: [-0.20, -0.10, -1],
  };
  for (const [leg, [x, y, side]] of Object.entries(geom)) {
    rows.push(
      {
        name: `${leg}_hip_joint`, type: "revolute", parent: "base_link", child: `${leg}_hip_link`,
        xyz: [x, y, 0], rpy: [0, 0, 0], axis: [1, 0, 0], lower: -1.2, upper: 1.2, effort: 35, velocity: 30,
      },
      {
        name: `${leg}_thigh_joint`, type: "revolute", parent: `${leg}_hip_link`, child: `${leg}_thigh_link`,
        xyz: [0, 0.08 * side, 0], rpy: [0, 0, 0], axis: [0, 1, 0], lower: -3, upper: 3, effort: 35, velocity: 30,
      },
      {
        name: `${leg}_calf_joint`, type: "revolute", parent: `${leg}_thigh_link`, child: `${leg}_calf_link`,
        xyz: [0, 0, -0.22], rpy: [0, 0, 0], axis: [0, 1, 0], lower: -2.8, upper: -0.45, effort: 45, velocity: 30,
      },
      {
        name: `${leg}_foot_fixed`, type: "fixed", parent: `${leg}_calf_link`, child: `${leg}_foot_link`,
        xyz: [0, 0, -0.22], rpy: [0, 0, 0], axis: [0, 0, 1], lower: 0, upper: 0, effort: 0, velocity: 0,
      },
    );
  }
  return rows;
}

function resetStepTemplate() {
  const template = el.stepTemplate.value;
  state.stepJoints = buildDefaultStepJoints();
  el.stepJointSection.style.display = "";
  el.stepCreateRobot.disabled = false;
  el.stepCreateRobot.checked = true;
  renderStepJointTable();
  renderJointMarkers();
  el.stepStatus.textContent = STEP_TEMPLATE_LABELS[template] || "ready";
  updateFlowStep();
}

function legacyOnStepFilePicked() {
  const files = Array.from(el.stepFile.files || []);
  el.stepError.textContent = "";
  el.stepResult.innerHTML = "";
  if (!files.length) {
    el.stepFileName.textContent = "请选择文件夹，不是单个 stp";
    state.parts = [];
    state.solids = [];
    state.selectedPartId = "";
    renderAssembly();
    return;
  }
  const mode = el.stepInputMode?.value || state.inputMode || "assembly";
  state.inputMode = mode;
  if (mode === "assembly" && files.length === 1 && CAD_MESH_EXTS.has(fileExt(files[0].name)) && [" .stp", ".step"].includes(fileExt(files[0].name))) {
    inspectSingleStep(files[0]);
    return;
  }
  const supported = files.filter((file) => CAD_MESH_EXTS.has(fileExt(file.name)));
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const folder = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : files[0].name;
  el.stepFileName.textContent = `${folder} / ${supported.length}/${files.length} 个 CAD 文件 / ${formatBytes(totalBytes)}`;
  if (!el.stepRobotName.value.trim()) {
    el.stepRobotName.value = folder.replace(/\.(stp|step|stl|dae|obj)$/i, "").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  }
  state.parts = supported.map((file, index) => buildPartState(file, index));
  state.solids = [];
  state.selectedPartId = state.parts[0]?.id || "";
  state.currentAssemblyLink = "base_link";
  renderAssembly();
}

async function legacyInspectSingleStep(file) {
  const totalBytes = file.size;
  el.stepFileName.textContent = `${file.name} / ${formatBytes(totalBytes)} / 正在识别 solids`;
  if (!el.stepRobotName.value.trim()) {
    el.stepRobotName.value = file.name.replace(/\.(stp|step)$/i, "").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  }
  const payload = new FormData();
  payload.append("file", file);
  payload.append("robot_name", el.stepRobotName.value.trim());
  payload.append("material", el.stepMaterial.value);
  payload.append("cad_unit", el.stepUnit.value);
  try {
    const result = await robots.inspectStepAssembly(payload);
    state.solids = (result.solids || []).map((solid, index) => ({
      id: solid.id || `solid_${index + 1}`,
      file: null,
      path: solid.path,
      name: solid.name || solid.mesh_name || `solid_${index + 1}`,
      ext: ".stl",
      size: 0,
      link: "",
      xyz: [0, 0, 0],
      rpy: [0, 0, 0],
      visual: true,
      collision: true,
      previewStatus: "ready",
      previewMessage: `solid ${index + 1}`,
      previewGeometry: null,
      previewPromise: null,
      meshUrl: solid.meshUrl || solid.mesh_url,
      meshName: solid.meshName || solid.mesh_name,
      volume_m3: solid.volume_m3 || 0,
      mass_kg: solid.mass_kg || 0,
      bbox: solid.bbox || [],
    }));
    state.parts = state.solids.map((solid, index) => ({
      id: solid.id,
      file: null,
      path: solid.path,
      name: solid.name,
      ext: ".stl",
      size: 0,
      link: "",
      xyz: [Number(((index % 5 - 2) * 0.18).toFixed(3)), Number((Math.floor(index / 5) * 0.13).toFixed(3)), 0],
      rpy: [0, 0, 0],
      visual: true,
      collision: true,
      previewStatus: "ready",
      previewMessage: "solid",
      previewGeometry: null,
      previewPromise: null,
      meshUrl: solid.meshUrl || solid.mesh_url,
      meshName: solid.meshName || solid.mesh_name,
    }));
    state.selectedPartId = state.parts[0]?.id || "";
    state.currentAssemblyLink = "base_link";
    renderAssembly();
    if (result.warnings?.length) {
      el.stepError.textContent = result.warnings.join("；");
    }
  } catch (err) {
    el.stepError.textContent = err instanceof ApiError ? err.message : "STEP solid 识别失败";
  }
}

function legacyBuildPartState(file, index) {
  const path = file.webkitRelativePath || file.name;
  const row = Math.floor(index / 5);
  const col = index % 5;
  return {
    id: `part_${index}_${Math.random().toString(16).slice(2)}`,
    file,
    path,
    name: file.name,
    ext: fileExt(file.name),
    size: file.size,
    link: "",
    xyz: [Number(((col - 2) * 0.18).toFixed(3)), Number((row * 0.13).toFixed(3)), 0],
    rpy: [0, 0, 0],
    visual: true,
    collision: true,
    previewStatus: "pending",
    previewMessage: fileExt(file.name) === ".dae" ? "DAE package export only" : "",
    previewGeometry: null,
    previewPromise: null,
    meshUrl: "",
  };
}

function legacyRenderAssembly() {
  renderPartList();
  renderAssignmentList();
  renderPartPreview();
  renderJointMarkers();
  updateFlowStep();
  updatePreviewStatus();
  updateAssemblySelectionPanel();
  const linked = state.parts.filter((p) => p.link).length;
  el.assemblyViewerLabel.textContent = state.parts.length ? `${state.parts.length} 个零件 / ${linked} 个已分配` : "等待选择文件夹";
}

function renderAssemblyControls() {
  if (el.assemblyActiveLink) {
    el.assemblyActiveLink.innerHTML = LINK_ORDER
      .map((link) => `<option value="${link}">${link}</option>`)
      .join("");
    el.assemblyActiveLink.value = state.currentAssemblyLink;
  }
  setTransformMode(state.transformMode, { quiet: true });
  setTransformSpace(state.transformSpace, { quiet: true });
  updateAssemblySelectionPanel();
}

function renderPartList() {
  if (!state.parts.length) {
    el.stepPartList.innerHTML = `<div class="step-empty">上传整机 STEP 后，这里会列出识别出来的 solids；文件夹模式则列出每个零件。</div>`;
    return;
  }
  el.stepPartList.innerHTML = state.parts.map((part) => `
    <button class="part-row${part.id === state.selectedPartId ? " active" : ""}" type="button" data-part-id="${escapeHtml(part.id)}">
      <span class="part-dot" style="background:#${partColor(part).toString(16).padStart(6, "0")}"></span>
      <span class="part-main">
        <b>${escapeHtml(part.name)}</b>
        <small>${escapeHtml(part.path)} / ${formatBytes(part.size)} / ${escapeHtml(previewStatusText(part))}</small>
      </span>
      <span class="part-link">${escapeHtml(part.link || "未分配")}</span>
    </button>
  `).join("");
  el.stepPartList.querySelectorAll("[data-part-id]").forEach((button) => {
    button.addEventListener("click", () => selectPart(button.dataset.partId));
  });
  updatePreviewStatus();
}

function renderAssignmentList() {
  if (!state.parts.length) {
    el.stepAssignmentList.innerHTML = `<div class="step-empty">先导入 STEP solids 或零件文件夹，再把实体分配给 base_link、fl_hip_link 等 link。</div>`;
    updateAssemblySelectionPanel();
    return;
  }
  const linkOptions = [`<option value="">不导出此零件</option>`, ...LINK_ORDER.map((link) => `<option value="${link}">${link}</option>`)].join("");
  el.stepAssignmentList.innerHTML = state.parts.map((part, index) => `
    <div class="assignment-row" data-part-id="${escapeHtml(part.id)}">
      <div class="assignment-name">
        <b>${escapeHtml(part.name)}</b>
        <small>${escapeHtml(part.path)}</small>
      </div>
      <select class="field" data-assign-field="link" data-index="${index}">${linkOptions}</select>
      <input class="field mono" data-assign-field="xyz" data-index="${index}" value="${escapeHtml(vecText(part.xyz))}" title="mesh origin xyz" />
      <input class="field mono" data-assign-field="rpy" data-index="${index}" value="${escapeHtml(vecText(part.rpy))}" title="mesh origin rpy" />
      <label class="mini-check"><input data-assign-field="visual" data-index="${index}" type="checkbox"${part.visual ? " checked" : ""} /> visual</label>
      <label class="mini-check"><input data-assign-field="collision" data-index="${index}" type="checkbox"${part.collision ? " checked" : ""} /> collision</label>
    </div>
  `).join("");
  el.stepAssignmentList.querySelectorAll('select[data-assign-field="link"]').forEach((select) => {
    const part = state.parts[Number(select.dataset.index)];
    select.value = part?.link || "";
  });
  el.stepAssignmentList.querySelectorAll("[data-assign-field]").forEach((input) => {
    input.addEventListener("input", onPartAssignmentInput);
    input.addEventListener("change", onPartAssignmentInput);
  });
}

function onPartAssignmentInput(event) {
  const input = event.currentTarget;
  const part = state.parts[Number(input.dataset.index)];
  const field = input.dataset.assignField;
  if (!part || !field) return;
  if (field === "xyz" || field === "rpy") part[field] = parseVec(input.value);
  else if (field === "visual" || field === "collision") part[field] = input.checked;
  else {
    part[field] = input.value;
    if (field === "link" && input.value) state.currentAssemblyLink = input.value;
  }
  renderPartList();
  renderPartPreview();
  updateFlowStep();
  updateAssemblySelectionPanel();
}

function renderPartPreview() {
  if (!viewer.partGroup) return;
  detachTransform();
  clearGroup(viewer.previewGroup);
  clearGroup(viewer.partGroup);
  state.partObjects.clear();
  if (!state.parts.length) {
    const empty = new THREE.Mesh(
      new THREE.BoxGeometry(0.34, 0.2, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7, metalness: 0.1 }),
    );
    empty.position.set(0, 0, 0.04);
    viewer.partGroup.add(empty);
    frameAssembly();
    updateAssemblySelectionPanel();
    return;
  }
  const selectedId = state.selectedPartId || state.parts[0]?.id || "";
  const assemblyBox = combineBoundingBoxes(state.solids);
  if (assemblyBox) state.assemblyBounds = assemblyBox;
  loadAssemblyPreviewGeometry()
    .then((geometry) => {
      if (!geometry || !viewer.previewGroup) return;
      clearGroup(viewer.previewGroup);
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshStandardMaterial({
          color: 0x38bdf8,
          roughness: 0.42,
          metalness: 0.15,
          transparent: true,
          opacity: 0.16,
          side: THREE.DoubleSide,
        }),
      );
      viewer.previewGroup.add(mesh);
      frameAssembly({ soft: false });
    })
    .catch(() => {});
  const isAssemblyMode = Boolean(state.currentAssemblyId);
  const renderParts = isAssemblyMode ? state.parts.filter((part) => part.id === selectedId) : state.parts;
  renderParts.forEach((part, index) => {
    const group = new THREE.Group();
    group.userData.partId = part.id;
    if (isAssemblyMode) {
      group.position.set(0, 0, 0);
      group.rotation.set(0, 0, 0);
      group.add(createPartMesh(part, assemblyProxyGeometry(part, index), true));
    } else {
      group.position.fromArray(part.xyz);
      group.rotation.set(...part.rpy);
      group.add(createPartMesh(part, placeholderGeometry(part, index), true));
    }
    viewer.partGroup.add(group);
    state.partObjects.set(part.id, group);

    if (part.ext === ".dae") return;
    if (isAssemblyMode && part.id !== selectedId) return;
    if (!isAssemblyMode && part.id !== selectedId && part.previewStatus !== "ready" && part.previewStatus !== "error") return;
    loadPartPreviewGeometry(part)
      .then((geometry) => {
        if (!viewer.partGroup || group.parent !== viewer.partGroup || !state.parts.includes(part)) return;
        clearGroup(group);
        group.add(createPartMesh(part, geometry, false));
        frameAssembly({ soft: true });
      })
      .catch((err) => {
        part.previewStatus = "error";
        part.previewMessage = err instanceof Error ? err.message : "preview failed";
        renderPartList();
      });
  });
  frameAssembly({ soft: true });
  attachTransformToSelection();
  updateAssemblySelectionPanel();
}

function createPartMesh(part, geometry, placeholder = false) {
  const material = new THREE.MeshStandardMaterial({
    color: partColor(part),
    roughness: placeholder ? 0.65 : 0.44,
    metalness: placeholder ? 0.06 : part.ext === ".stp" || part.ext === ".step" ? 0.32 : 0.12,
    transparent: !part.link || placeholder,
    opacity: placeholder ? 0.26 : part.link ? 0.94 : 0.42,
    side: THREE.DoubleSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.partId = part.id;
  mesh.userData.placeholder = placeholder;
  return mesh;
}

async function loadPartPreviewGeometry(part) {
  if (part.previewGeometry) return part.previewGeometry.clone();
  if (!part.previewPromise) {
    part.previewPromise = fetchPartPreviewGeometry(part)
      .then((geometry) => {
        part.previewGeometry = geometry;
        part.previewStatus = "ready";
        part.previewMessage = "mesh ready";
        renderPartList();
        return geometry;
      })
      .catch((err) => {
        part.previewPromise = null;
        throw err;
      });
  }
  const geometry = await part.previewPromise;
  return geometry.clone();
}

async function legacyFetchPartPreviewGeometry(part) {
  part.previewStatus = "loading";
  part.previewMessage = "loading mesh";
  renderPartList();

  const key = previewCacheKey(part);
  if (state.meshCache.has(key)) return state.meshCache.get(key).clone();

  let ext = part.ext;
  let buffer;
  const meshUrl = resolvePartMeshUrl(part);
  if (meshUrl) {
    const res = await fetch(meshUrl, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(formatPreviewError(res.status, text));
    }
    buffer = await res.arrayBuffer();
    ext = ".stl";
  } else if (ext === ".stp" || ext === ".step") {
    if (!part.file) {
      throw new Error("预览源缺失，请重新识别 STEP solids");
    }
    const payload = new FormData();
    payload.append("file", part.file);
    const res = await fetch("/api/robots/urdf/preview-mesh", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      body: payload,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(formatPreviewError(res.status, text));
    }
    buffer = await res.arrayBuffer();
    ext = ".stl";
  } else {
    if (!part.file || typeof part.file.arrayBuffer !== "function") {
      throw new Error("预览源缺失，请重新识别 CAD 文件");
    }
    buffer = await part.file.arrayBuffer();
  }

  let geometry;
  if (ext === ".stl") geometry = parseStlGeometry(buffer);
  else if (ext === ".obj") geometry = parseObjGeometry(new TextDecoder().decode(buffer));
  else throw new Error(`${ext || "mesh"} preview is not available yet`);

  normalizePreviewGeometry(geometry);
  state.meshCache.set(key, geometry.clone());
  return geometry;
}

function parseStlGeometry(buffer) {
  if (buffer.byteLength >= 84) {
    const view = new DataView(buffer);
    const faces = view.getUint32(80, true);
    if (84 + faces * 50 === buffer.byteLength) return parseBinaryStl(view, faces);
  }
  return parseAsciiStl(new TextDecoder().decode(buffer));
}

function parseBinaryStl(view, faces) {
  const positions = new Float32Array(faces * 9);
  let out = 0;
  let offset = 84;
  for (let i = 0; i < faces; i++) {
    offset += 12;
    for (let v = 0; v < 3; v++) {
      positions[out++] = view.getFloat32(offset, true);
      positions[out++] = view.getFloat32(offset + 4, true);
      positions[out++] = view.getFloat32(offset + 8, true);
      offset += 12;
    }
    offset += 2;
  }
  return geometryFromPositions(positions);
}

function parseAsciiStl(text) {
  const vertices = [];
  const re = /vertex\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)/gi;
  let match;
  while ((match = re.exec(text))) vertices.push(Number(match[1]), Number(match[2]), Number(match[3]));
  if (vertices.length < 9) throw new Error("STL has no triangles");
  return geometryFromPositions(new Float32Array(vertices));
}

function parseObjGeometry(text) {
  const verts = [];
  const positions = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const parts = line.split(/\s+/);
    if (parts[0] === "v" && parts.length >= 4) {
      verts.push([Number(parts[1]), Number(parts[2]), Number(parts[3])]);
    } else if (parts[0] === "f" && parts.length >= 4) {
      const face = parts.slice(1).map((token) => {
        const idx = Number(token.split("/")[0]);
        return idx < 0 ? verts.length + idx : idx - 1;
      }).filter((idx) => idx >= 0 && idx < verts.length);
      for (let i = 1; i < face.length - 1; i++) {
        for (const idx of [face[0], face[i], face[i + 1]]) positions.push(...verts[idx]);
      }
    }
  }
  if (positions.length < 9) throw new Error("OBJ has no triangles");
  return geometryFromPositions(new Float32Array(positions));
}

/**
 * 解析 COLLADA (.dae) 文件，返回 THREE.BufferGeometry。
 * 支持标准 COLLADA 1.4/1.5 triangles + polylist（需已三角化）。
 */
function parseDaeGeometry(text) {
  const doc = new DOMParser().parseFromString(text, "text/xml");
  if (doc.querySelector("parsererror")) return null;

  // 用 getElementsByTagName 忽略命名空间前缀，兼容各浏览器
  const all = (parent, tag) => Array.from(parent.getElementsByTagName(tag));

  // 收集所有 <source id="..."><float_array> 数据
  const srcData = new Map();
  for (const srcEl of all(doc, "source")) {
    const id = srcEl.getAttribute("id");
    const fa = all(srcEl, "float_array")[0];
    if (id && fa) srcData.set(id, fa.textContent.trim().split(/\s+/).map(Number));
  }

  // <vertices id="..."> 映射到 POSITION source id
  const vertexToPos = new Map();
  for (const vEl of all(doc, "vertices")) {
    const vid = vEl.getAttribute("id");
    for (const inp of all(vEl, "input")) {
      if (inp.getAttribute("semantic") === "POSITION") {
        vertexToPos.set(vid, inp.getAttribute("source")?.replace(/^#/, "") || "");
      }
    }
  }

  const outPositions = [];

  // 处理 <triangles> 和已三角化的 <polylist>
  const processPrimitive = (el) => {
    const inputs = all(el, "input");
    let vertOffset = 0;
    let vertSrcId = "";
    let maxOffset = 0;
    for (const inp of inputs) {
      const offset = parseInt(inp.getAttribute("offset") || "0");
      if (offset > maxOffset) maxOffset = offset;
      if (inp.getAttribute("semantic") === "VERTEX") {
        vertOffset = offset;
        vertSrcId = inp.getAttribute("source")?.replace(/^#/, "") || "";
      }
    }
    const stride = maxOffset + 1;

    // 解析 vcount（polylist）：只处理全是三角形的情况
    const vcountEl = all(el, "vcount")[0];
    let triOnly = true;
    if (vcountEl) {
      const vcounts = vcountEl.textContent.trim().split(/\s+/).map(Number);
      triOnly = vcounts.every((v) => v === 3);
      if (!triOnly) return; // 跳过非三角化 polylist
    }

    const pEl = all(el, "p")[0];
    if (!pEl) return;
    const indices = pEl.textContent.trim().split(/\s+/).map(Number);

    // 解析 vertex source → position array
    const posId = vertexToPos.get(vertSrcId) || vertSrcId;
    const pos = srcData.get(posId);
    if (!pos) return;

    for (let i = 0; i + stride - 1 < indices.length; i += stride) {
      const vi = indices[i + vertOffset] * 3;
      outPositions.push(pos[vi], pos[vi + 1], pos[vi + 2]);
    }
  };

  for (const el of all(doc, "triangles")) processPrimitive(el);
  for (const el of all(doc, "polylist")) processPrimitive(el);

  if (outPositions.length < 9) return null;
  return geometryFromPositions(new Float32Array(outPositions));
}

function geometryFromPositions(positions) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function legacyNormalizePreviewGeometry(geometry) {
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  if (!box || box.isEmpty()) return geometry;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  geometry.translate(-center.x, -center.y, -center.z);
  if (maxDim > 1e-9) {
    let scale = 1;
    if (maxDim > 2) scale = 0.42 / maxDim;
    else if (maxDim < 0.04) scale = 0.12 / maxDim;
    geometry.scale(scale, scale, scale);
  }
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function placeholderGeometry(part, index) {
  const byteScale = Math.min(1.6, Math.max(0.65, Math.log10(Math.max(part.size, 1000)) / 5));
  if (part.link === "base_link" || /base|trunk|body/i.test(part.name)) {
    return new THREE.BoxGeometry(0.44 * byteScale, 0.22 * byteScale, 0.1 * byteScale);
  }
  if (/foot|toe/i.test(part.name)) {
    return new THREE.SphereGeometry(0.045 * byteScale, 18, 12);
  }
  if (/calf|shank|lower/i.test(part.name)) {
    return new THREE.CapsuleGeometry(0.025 * byteScale, 0.2 * byteScale, 8, 16);
  }
  const len = 0.13 + (index % 3) * 0.025;
  return new THREE.BoxGeometry(0.07 * byteScale, len * byteScale, 0.055 * byteScale);
}

function renderJointMarkers() {
  if (!viewer.jointGroup) return;
  clearGroup(viewer.jointGroup);
  const joints = collectStepJoints({ fromDom: true, quiet: true });
  for (const joint of joints) {
    const origin = new THREE.Vector3(...joint.xyz);
    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(0.014, 12, 8),
      new THREE.MeshBasicMaterial({ color: joint.type === "fixed" ? 0x94a3b8 : 0xffffff }),
    );
    ball.position.copy(origin);
    viewer.jointGroup.add(ball);
    if (joint.type !== "fixed") {
      const axis = new THREE.Vector3(...joint.axis);
      if (axis.lengthSq() < 1e-6) axis.set(0, 0, 1);
      axis.normalize();
      const arrow = new THREE.ArrowHelper(axis, origin, 0.09, 0xffffff, 0.03, 0.018);
      viewer.jointGroup.add(arrow);
    }
  }
}

function selectPart(id) {
  state.selectedPartId = id || "";
  renderAssembly();
  focusSelectedPart({ keepDistance: true });
  attachTransformToSelection();
  updateAssemblySelectionPanel();
  const part = selectedPart();
  if (part && part.previewStatus !== "ready" && part.ext !== ".dae") {
    loadPartPreviewGeometry(part).catch(() => {});
  }
}

function selectedPart() {
  return state.parts.find((part) => part.id === state.selectedPartId) || null;
}

function assignSelectedPartToLink() {
  const part = selectedPart();
  if (!part) return;
  part.link = state.currentAssemblyLink || "base_link";
  renderPartList();
  renderAssignmentList();
  renderPartPreview();
  updateFlowStep();
  updateAssemblySelectionPanel();
}

function unassignSelectedPart() {
  const part = selectedPart();
  if (!part) return;
  part.link = "";
  renderPartList();
  renderAssignmentList();
  renderPartPreview();
  updateFlowStep();
  updateAssemblySelectionPanel();
}

function focusSelectedPart({ keepDistance = false } = {}) {
  const obj = state.partObjects.get(state.selectedPartId);
  if (!obj || !viewer.camera || !viewer.controls) return;
  const box = new THREE.Box3().setFromObject(obj);
  const center = box.isEmpty() ? obj.position.clone() : box.getCenter(new THREE.Vector3());
  const size = box.isEmpty() ? new THREE.Vector3(0.24, 0.24, 0.24) : box.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z, 0.18);
  viewer.controls.target.copy(center);
  if (!keepDistance) {
    viewer.camera.position.copy(center).add(new THREE.Vector3(radius * 1.8, -radius * 2.2, radius * 1.35));
  } else if (viewer.camera.position.distanceTo(center) < radius * 1.8) {
    viewer.camera.position.copy(center).add(new THREE.Vector3(radius * 1.8, -radius * 2.2, radius * 1.35));
  }
  viewer.controls.update();
}

function attachTransformToSelection() {
  const obj = state.partObjects.get(state.selectedPartId);
  if (!viewer.transform || !obj) {
    detachTransform();
    return;
  }
  viewer.transform.attach(obj);
  viewer.transform.visible = true;
  viewer.transform.enabled = true;
  viewer.transform.setMode(state.transformMode);
  viewer.transform.setSpace(state.transformSpace);
}

function detachTransform() {
  if (!viewer.transform) return;
  viewer.transform.detach();
  viewer.transform.visible = false;
  viewer.transform.enabled = false;
}

function setTransformMode(mode, { quiet = false } = {}) {
  const next = mode === "rotate" ? "rotate" : "translate";
  state.transformMode = next;
  viewer.transform?.setMode(next);
  el.transformTranslate?.classList.toggle("active", next === "translate");
  el.transformRotate?.classList.toggle("active", next === "rotate");
  if (!quiet) updateAssemblySelectionPanel();
}

function setTransformSpace(space, { quiet = false } = {}) {
  const next = space === "world" ? "world" : "local";
  state.transformSpace = next;
  viewer.transform?.setSpace(next);
  if (el.transformSpace) el.transformSpace.value = next;
  if (!quiet) updateAssemblySelectionPanel();
}

function onTransformObjectChange() {
  const part = selectedPart();
  const obj = state.partObjects.get(state.selectedPartId);
  if (!part || !obj) return;
  part.xyz = [obj.position.x, obj.position.y, obj.position.z].map(roundPose);
  part.rpy = [obj.rotation.x, obj.rotation.y, obj.rotation.z].map(roundPose);
  syncAssignmentInputs(part);
  updateAssemblySelectionPanel();
  updateFlowStep();
}

function syncAssignmentInputs(part) {
  const index = state.parts.indexOf(part);
  if (index < 0 || !el.stepAssignmentList) return;
  const xyz = el.stepAssignmentList.querySelector(`[data-assign-field="xyz"][data-index="${index}"]`);
  const rpy = el.stepAssignmentList.querySelector(`[data-assign-field="rpy"][data-index="${index}"]`);
  const link = el.stepAssignmentList.querySelector(`[data-assign-field="link"][data-index="${index}"]`);
  if (xyz) xyz.value = vecText(part.xyz);
  if (rpy) rpy.value = vecText(part.rpy);
  if (link) link.value = part.link || "";
}

function updateAssemblySelectionPanel() {
  const part = selectedPart();
  if (el.assemblyActiveLink) el.assemblyActiveLink.value = state.currentAssemblyLink || "base_link";
  if (el.transformSpace) el.transformSpace.value = state.transformSpace;
  el.transformTranslate?.classList.toggle("active", state.transformMode === "translate");
  el.transformRotate?.classList.toggle("active", state.transformMode === "rotate");
  const hasSelection = Boolean(part);
  if (el.assignSelectedPart) el.assignSelectedPart.disabled = !hasSelection;
  if (el.unassignSelectedPart) el.unassignSelectedPart.disabled = !hasSelection;
  if (el.focusSelectedPart) el.focusSelectedPart.disabled = !hasSelection;
  if (!el.assemblySelection) return;
  if (!state.parts.length) {
    el.assemblySelection.innerHTML = "先选择一个 CAD 文件夹，然后按 SolidWorks URDF exporter 的顺序装配 link。";
    return;
  }
  if (!part) {
    el.assemblySelection.innerHTML = "在 3D 视窗里点击实体，或从零件清单选择实体。";
    return;
  }
  el.assemblySelection.innerHTML = `
    <div class="selection-title">${escapeHtml(part.name)}</div>
    <div class="selection-grid">
      <span>当前归属</span><b>${escapeHtml(part.link || "未分配")}</b>
      <span>准备加入</span><b>${escapeHtml(state.currentAssemblyLink || "base_link")}</b>
      <span>origin xyz</span><code>${escapeHtml(vecText(part.xyz))}</code>
      <span>origin rpy</span><code>${escapeHtml(vecText(part.rpy))}</code>
    </div>`;
}

function onViewerPointerDown(event) {
  if (!viewer.camera || !viewer.renderer || viewer.isTransformDragging || viewer.ignoreNextPick) return;
  if (event.button !== 0) return;
  const rect = viewer.renderer.domElement.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  viewer.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  viewer.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  viewer.raycaster.setFromCamera(viewer.pointer, viewer.camera);
  const meshes = [];
  viewer.partGroup?.traverse((node) => {
    if (node.isMesh && node.userData.partId) meshes.push(node);
  });
  const hit = viewer.raycaster.intersectObjects(meshes, false)[0];
  if (!hit?.object?.userData.partId) return;
  selectPart(hit.object.userData.partId);
}

function roundPose(value) {
  return Number((Number(value) || 0).toFixed(5));
}

function frameAssembly({ soft = false } = {}) {
  if (!viewer.camera || !viewer.controls) return;
  const box = new THREE.Box3();
  let hasBox = false;
  for (const group of [viewer.previewGroup, viewer.partGroup]) {
    if (!group) continue;
    const groupBox = new THREE.Box3().setFromObject(group);
    if (!groupBox.isEmpty()) {
      box.union(groupBox);
      hasBox = true;
    }
  }
  if (!hasBox || box.isEmpty()) {
    viewer.camera.position.set(1.2, -1.5, 0.9);
    viewer.controls.target.set(0, 0, 0);
    return;
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z, 0.45);
  if (!soft || viewer.controls.target.distanceTo(center) > radius * 2) {
    viewer.controls.target.copy(center);
    viewer.camera.position.copy(center).add(new THREE.Vector3(radius * 1.3, -radius * 1.7, radius * 1.05));
  }
}
function normalizeName(name) {
  return String(name || "")
    .toLowerCase()
    .replace(/left/g, "l")
    .replace(/right/g, "r")
    .replace(/front/g, "f")
    .replace(/rear|hind/g, "r")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function partColor(part) {
  return LINK_COLORS[part.link] || 0x64748b;
}

function retryPreviewMeshes() {
  for (const geometry of state.meshCache.values()) geometry.dispose?.();
  state.meshCache.clear();
  state.assemblyPreviewGeometry?.dispose?.();
  state.assemblyPreviewGeometry = null;
  state.assemblyPreviewPromise = null;
  for (const part of state.parts) {
    part.previewGeometry?.dispose?.();
    part.previewGeometry = null;
    part.previewPromise = null;
    part.previewStatus = "pending";
    part.previewMessage = part.ext === ".dae" ? "DAE package export only" : "";
  }
  renderAssembly();
}

function legacySyncInputMode() {
  if (!el.stepInputMode) return;
  const assembly = state.inputMode === "assembly";
  el.stepFileName.textContent = assembly ? "支持单个整机 STEP，也支持文件夹" : "请选择文件夹，不是单个 stp";
  updatePreviewStatus();
}

function legacyPreviewCacheKey(part) {
  return `${part.path}:${part.size}:${part.file.lastModified || 0}`;
}

function previewStatusText(part) {
  if (part.ext === ".dae") return "DAE package export only";
  if (part.previewStatus === "ready") return "mesh ready";
  if (part.previewStatus === "loading") return "loading mesh";
  if (part.previewStatus === "error") return `preview failed: ${part.previewMessage || ""}`;
  return "waiting preview";
}

function updatePreviewStatus() {
  if (!el.assemblyPreviewStatus) return;
  const previewable = state.parts.filter((part) => part.ext !== ".dae");
  const total = previewable.length;
  const ready = previewable.filter((part) => part.previewStatus === "ready").length;
  const loading = previewable.filter((part) => part.previewStatus === "loading").length;
  const failedParts = previewable.filter((part) => part.previewStatus === "error");
  const failed = failedParts.length;
  let status = "idle";
  let text = "等待选择 CAD 零件文件夹";
  if (state.parts.length && !total) {
    text = "当前文件只参与导出，暂不支持网页预览";
  } else if (total) {
    status = failed ? "error" : loading ? "loading" : ready === total ? "ok" : "idle";
    if (failed) {
      const first = failedParts[0]?.previewMessage || "unknown error";
      text = `真实网格 ${ready}/${total}，${failed} 个失败；先显示占位预览。${first}`;
    } else if (loading) {
      text = `真实网格加载中 ${ready}/${total}`;
    } else if (ready === total) {
      text = `真实网格已加载 ${ready}/${total}`;
    } else {
      text = `等待真实网格 ${ready}/${total}`;
    }
  }
  el.assemblyPreviewStatus.textContent = text;
  el.assemblyPreviewStatus.dataset.status = status;
}

function formatPreviewError(status, text) {
  if (status === 404 || status === 405) {
    return `预览接口不可用 HTTP ${status}，请重启后端服务`;
  }
  if (!text) return `STEP preview failed (${status})`;
  try {
    const data = JSON.parse(text);
    const detail = data.detail || data.error || data.message;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
    return JSON.stringify(detail || data);
  } catch {
    return text.slice(0, 240);
  }
}

function updateFlowStep() {
  const parts = state.parts.length;
  const linked = state.parts.filter((p) => p.link).length;
  const joints = state.stepJoints.length;
  const active = !parts ? 1 : linked < parts ? 2 : joints ? 3 : 4;
  document.querySelectorAll("[data-flow-step]").forEach((node) => {
    node.classList.toggle("active", Number(node.dataset.flowStep) === active);
    node.classList.toggle("done", Number(node.dataset.flowStep) < active);
  });
}

function renderStepJointTable() {
  if (!state.stepJoints.length) {
    el.stepJointTable.innerHTML = `<div class="step-empty">单刚体模板不需要关节；导出的 URDF 只有 base_link。</div>`;
    return;
  }
  const typeOptions = ["revolute", "fixed", "continuous", "prismatic"];
  let html = `
    <div class="sj-head">joint</div><div class="sj-head">type</div><div class="sj-head">parent</div>
    <div class="sj-head">child</div><div class="sj-head">origin xyz</div><div class="sj-head">origin rpy</div>
    <div class="sj-head">axis</div><div class="sj-head">limit</div>`;
  state.stepJoints.forEach((joint, index) => {
    const options = typeOptions.map((type) => `<option value="${type}"${joint.type === type ? " selected" : ""}>${type}</option>`).join("");
    html += `
      <input class="field" data-step-index="${index}" data-field="name" value="${escapeHtml(joint.name)}" />
      <select class="field" data-step-index="${index}" data-field="type">${options}</select>
      <input class="field" data-step-index="${index}" data-field="parent" value="${escapeHtml(joint.parent)}" />
      <input class="field" data-step-index="${index}" data-field="child" value="${escapeHtml(joint.child)}" />
      <input class="field sj-mono" data-step-index="${index}" data-field="xyz" value="${escapeHtml(vecText(joint.xyz))}" />
      <input class="field sj-mono" data-step-index="${index}" data-field="rpy" value="${escapeHtml(vecText(joint.rpy))}" />
      <input class="field sj-mono" data-step-index="${index}" data-field="axis" value="${escapeHtml(vecText(joint.axis))}" />
      <div class="limit-mini">
        <input class="field" type="number" step="0.01" data-step-index="${index}" data-field="lower" value="${num(joint.lower, 0)}" />
        <input class="field" type="number" step="0.01" data-step-index="${index}" data-field="upper" value="${num(joint.upper, 0)}" />
      </div>`;
  });
  el.stepJointTable.innerHTML = html;
  el.stepJointTable.querySelectorAll("[data-step-index]").forEach((input) => {
    input.addEventListener("input", () => renderJointMarkers());
    input.addEventListener("change", () => renderJointMarkers());
  });
}

function collectStepJoints({ fromDom = true, quiet = false } = {}) {
  const rows = state.stepJoints.map((joint) => ({ ...joint, xyz: [...joint.xyz], rpy: [...joint.rpy], axis: [...joint.axis] }));
  if (!fromDom || !el.stepJointTable) return rows;
  el.stepJointTable.querySelectorAll("[data-step-index]").forEach((input) => {
    const row = rows[Number(input.dataset.stepIndex)];
    const field = input.dataset.field;
    if (!row || !field) return;
    if (field === "xyz" || field === "rpy" || field === "axis") row[field] = parseVec(input.value);
    else if (field === "lower" || field === "upper") row[field] = num(input.value, 0);
    else row[field] = input.value.trim();
  });
  if (!quiet) state.stepJoints = rows;
  return rows;
}

function legacyCollectPartAssignments() {
  return state.parts
    .filter((part) => part.link)
    .map((part) => ({
      path: part.path,
      link: part.link,
      xyz: part.xyz,
      rpy: part.rpy,
      visual: part.visual,
      collision: part.collision,
    }));
}

async function legacyOnStepExport(e) {
  e.preventDefault();
  el.stepError.textContent = "";
  el.stepResult.innerHTML = "";
  const files = Array.from(el.stepFile.files || []);
  if (!files.length) {
    el.stepError.textContent = "请先选择 CAD 零件文件夹";
    return;
  }
  if (files.some((file) => !file.webkitRelativePath)) {
    el.stepError.textContent = "这里需要选择整个 CAD 导出目录，不是单个文件";
    return;
  }
  if (!files.some((file) => CAD_MESH_EXTS.has(fileExt(file.name)))) {
    el.stepError.textContent = "文件夹里没有 .stp/.step/.stl/.dae/.obj 文件";
    return;
  }
  if (!el.stepRobotName.value.trim()) {
    el.stepError.textContent = "机器人名称不能为空";
    return;
  }
  const assignments = collectPartAssignments();
  if (!assignments.length) {
    el.stepError.textContent = "至少需要把一个零件分配到 URDF link";
    return;
  }

  const payload = new FormData();
  for (const file of files) {
    payload.append("files", file);
    payload.append("relative_paths", file.webkitRelativePath || file.name);
  }
  payload.append("robot_name", el.stepRobotName.value.trim());
  payload.append("vendor", el.stepVendor.value.trim());
  payload.append("template", el.stepTemplate.value);
  payload.append("material", el.stepMaterial.value);
  payload.append("cad_unit", el.stepUnit.value);
  payload.append("create_robot", el.stepCreateRobot.checked ? "true" : "false");
  payload.append("joints_json", JSON.stringify(collectStepJoints()));
  payload.append("part_assignments_json", JSON.stringify(assignments));

  el.stepExportButton.disabled = true;
  el.stepStatus.textContent = "导出中";
  try {
    const result = await robots.exportStepFolderUrdf(payload);
    renderStepResult(result);
    el.stepStatus.textContent = "已生成 URDF package";
    if (result.robot_id) {
      await loadList();
      await selectRobot(result.robot_id);
    }
  } catch (err) {
    el.stepError.textContent = err instanceof ApiError ? err.message : "导出失败";
    el.stepStatus.textContent = "导出失败";
  } finally {
    el.stepExportButton.disabled = false;
  }
}

function onUrdfFilePicked() {
  const file = el.urdfUploadFile.files && el.urdfUploadFile.files[0];
  if (!file) return;
  state.urdfFolderFiles = null;
  state.urdfFolderMode = false;
  el.urdfUploadFileName.textContent = `${file.name} / ${formatBytes(file.size)}`;
  if (!el.urdfRobotName.value.trim()) {
    el.urdfRobotName.value = file.name.replace(/\.(urdf|zip)$/i, "").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  }
}

function onUrdfFolderInputPicked() {
  const files = Array.from(el.urdfFolderInput.files || []);
  if (!files.length) return;
  const folderName = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : "folder";
  state.urdfFolderFiles = files.map((f) => ({ file: f, relPath: f.webkitRelativePath || f.name }));
  state.urdfFolderMode = true;
  el.urdfUploadFileName.textContent = `${folderName}/ — ${files.length} 个文件`;
  if (!el.urdfRobotName.value.trim()) {
    el.urdfRobotName.value = folderName.replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  }
}

function onUrdfDropZoneClick() {
  // Offer both folder and file; prefer folder picker via the hidden folder input.
  el.urdfFolderInput.click();
}

async function onUrdfDrop(e) {
  e.preventDefault();
  el.urdfDropZone?.classList.remove("drag-over");
  el.urdfUploadError.textContent = "";

  const items = Array.from(e.dataTransfer?.items || []);
  const dtFiles = Array.from(e.dataTransfer?.files || []);

  // Try to get entries via File System Access API for proper relative paths.
  const entries = items.map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (entries.length) {
    try {
      const collected = await collectEntriesRecursive(entries);
      if (collected.length) {
        const folderName = entries[0].isDirectory ? entries[0].name : (collected[0].relPath.split("/")[0] || "folder");
        state.urdfFolderFiles = collected;
        state.urdfFolderMode = true;
        el.urdfUploadFileName.textContent = `${folderName}/ — ${collected.length} 个文件`;
        if (!el.urdfRobotName.value.trim()) {
          el.urdfRobotName.value = folderName.replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
        }
        return;
      }
    } catch {
      // fall through to dtFiles
    }
  }

  // Fallback: plain files (e.g. drag a .urdf or .zip directly).
  if (dtFiles.length === 1 && /\.(urdf|zip)$/i.test(dtFiles[0].name)) {
    state.urdfFolderFiles = null;
    state.urdfFolderMode = false;
    el.urdfUploadFileName.textContent = `${dtFiles[0].name} / ${formatBytes(dtFiles[0].size)}`;
    // Shim into the hidden file input so onUrdfUpload picks it up.
    const dt = new DataTransfer();
    dt.items.add(dtFiles[0]);
    el.urdfUploadFile.files = dt.files;
    if (!el.urdfRobotName.value.trim()) {
      el.urdfRobotName.value = dtFiles[0].name.replace(/\.(urdf|zip)$/i, "").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
    }
  } else if (dtFiles.length > 1) {
    // Multiple files dropped — treat as a folder.
    state.urdfFolderFiles = dtFiles.map((f) => ({ file: f, relPath: f.webkitRelativePath || f.name }));
    state.urdfFolderMode = true;
    const folderName = dtFiles[0].webkitRelativePath?.split("/")[0] || "folder";
    el.urdfUploadFileName.textContent = `${folderName}/ — ${dtFiles.length} 个文件`;
    if (!el.urdfRobotName.value.trim()) {
      el.urdfRobotName.value = folderName.replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
    }
  }
}

/** Recursively collect all files from a list of FileSystemEntry objects. */
async function collectEntriesRecursive(entries, prefix = "") {
  const result = [];
  for (const entry of entries) {
    if (entry.isFile) {
      const file = await new Promise((res, rej) => entry.file(res, rej));
      result.push({ file, relPath: prefix + entry.name });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const children = await new Promise((res, rej) => reader.readEntries(res, rej));
      result.push(...await collectEntriesRecursive(children, prefix + entry.name + "/"));
    }
  }
  return result;
}

async function onUrdfUpload(e) {
  e.preventDefault();
  el.urdfUploadError.textContent = "";
  el.urdfUploadResult.innerHTML = "";

  if (state.urdfFolderMode && state.urdfFolderFiles?.length) {
    await uploadUrdfFolderFiles(state.urdfFolderFiles);
    return;
  }

  const file = el.urdfUploadFile.files && el.urdfUploadFile.files[0];
  if (!file) {
    el.urdfUploadError.textContent = "请先拖入 URDF 文件夹，或点击选择 .urdf / .zip 文件";
    return;
  }

  const payload = new FormData();
  payload.append("file", file);
  payload.append("robot_name", el.urdfRobotName.value.trim());
  payload.append("vendor", el.urdfVendor.value.trim());
  payload.append("morphology", el.urdfMorphology.value);
  payload.append("create_robot", el.urdfCreateRobot.checked ? "true" : "false");
  payload.append("simplify_meshes", el.urdfSimplifyMeshes.checked ? "true" : "false");

  el.urdfUploadButton.disabled = true;
  el.urdfUploadStatus.textContent = "上传中";
  try {
    const result = await robots.uploadUrdf(payload);
    renderUrdfUploadResult(result);
    el.urdfUploadStatus.textContent = result.robot_id ? "已加入机器人列表" : "已保存 package";
    if (result.robot_id) {
      await loadList();
      await selectRobot(result.robot_id, { autoOpenModal: true });
    }
  } catch (err) {
    el.urdfUploadError.textContent = err instanceof ApiError ? err.message : "上传失败";
    el.urdfUploadStatus.textContent = "上传失败";
  } finally {
    el.urdfUploadButton.disabled = false;
  }
}

async function uploadUrdfFolderFiles(folderFiles) {
  const payload = new FormData();
  for (const { file, relPath } of folderFiles) {
    payload.append("files", file);
    payload.append("relative_paths", relPath);
  }
  payload.append("robot_name", el.urdfRobotName.value.trim());
  payload.append("vendor", el.urdfVendor.value.trim());
  payload.append("morphology", el.urdfMorphology.value);
  payload.append("create_robot", el.urdfCreateRobot.checked ? "true" : "false");
  payload.append("simplify_meshes", el.urdfSimplifyMeshes.checked ? "true" : "false");

  el.urdfUploadButton.disabled = true;
  el.urdfUploadStatus.textContent = `上传中 (${folderFiles.length} 个文件)`;
  try {
    const result = await robots.uploadUrdfFolder(payload);
    renderUrdfUploadResult(result);
    el.urdfUploadStatus.textContent = result.robot_id ? "已加入机器人列表" : "已保存 package";
    if (result.robot_id) {
      await loadList();
      await selectRobot(result.robot_id, { autoOpenModal: true });
    }
  } catch (err) {
    el.urdfUploadError.textContent = err instanceof ApiError ? err.message : "上传失败";
    el.urdfUploadStatus.textContent = "上传失败";
  } finally {
    el.urdfUploadButton.disabled = false;
  }
}

function renderUrdfUploadResult(result) {
  const warnings = (result.warnings || []).map((w) => `<div class="step-warning">${escapeHtml(w)}</div>`).join("");
  const joints = (result.detected_joints || []).slice(0, 24).map((name) => `<span>${escapeHtml(name)}</span>`).join("");
  const robotLink = result.robot_id
    ? `<a class="btn" href="/robots/?robot=${encodeURIComponent(result.robot_id)}">打开机器人配置</a>`
    : "";
  el.urdfUploadResult.innerHTML = `
    <div class="step-result-head">
      <strong>${escapeHtml(result.robot_name)}</strong>
      <span>${escapeHtml(result.asset_name)}</span>
    </div>
    <div class="step-result-actions">
      <a class="primary" href="${escapeHtml(result.download_url)}">下载 package zip</a>
      <a class="btn" href="${escapeHtml(result.urdf_url)}" target="_blank" rel="noreferrer">查看 URDF</a>
      ${robotLink}
    </div>
    <div class="step-meta">
      <span>urdf: ${escapeHtml(result.urdf_ref || "")}</span>
      <span>joints: ${(result.detected_joints || []).length}</span>
      <span>mesh: ${result.simplify_meshes === false ? "original" : "simplified"}</span>
    </div>
    ${joints ? `<div class="step-detected"><b>detected</b>${joints}</div>` : ""}
    ${warnings}`;
}

// ── URDF 3D Viewer: parse + kinematic chain ──────────────────────────────────

/**
 * Parse a URDF XML string into a lightweight kinematic description.
 * Returns { robotName, links, joints } where:
 *   links  → Map<name, { name, visual: [{filename,xyz,rpy,scale}] }>
 *   joints → [{name,type,parent,child,xyz,rpy,axis}]
 */
function parseUrdfXml(xmlText) {
  const doc = new DOMParser().parseFromString(xmlText, "text/xml");
  const robotEl = doc.querySelector("robot");
  const robotName = robotEl?.getAttribute("name") || "";

  const links = new Map();
  for (const linkEl of doc.querySelectorAll("link")) {
    const name = linkEl.getAttribute("name") || "";
    if (!name) continue;
    const visuals = [];
    for (const visual of linkEl.querySelectorAll("visual")) {
      const meshEl = visual.querySelector("geometry > mesh");
      if (!meshEl) continue;
      const originEl = visual.querySelector("origin");
      visuals.push({
        filename: meshEl.getAttribute("filename") || "",
        scale: urdfParseVec3(meshEl.getAttribute("scale"), [1, 1, 1]),
        xyz: urdfParseVec3(originEl?.getAttribute("xyz")),
        rpy: urdfParseVec3(originEl?.getAttribute("rpy")),
      });
    }
    links.set(name, { name, visual: visuals });
  }

  const joints = [];
  for (const jointEl of doc.querySelectorAll("joint")) {
    const name = jointEl.getAttribute("name") || "";
    const type = jointEl.getAttribute("type") || "fixed";
    const parent = jointEl.querySelector("parent")?.getAttribute("link") || "";
    const child = jointEl.querySelector("child")?.getAttribute("link") || "";
    const originEl = jointEl.querySelector("origin");
    const axisEl = jointEl.querySelector("axis");
    if (!name || !parent || !child) continue;
    joints.push({
      name,
      type,
      parent,
      child,
      xyz: urdfParseVec3(originEl?.getAttribute("xyz")),
      rpy: urdfParseVec3(originEl?.getAttribute("rpy")),
      axis: urdfParseVec3(axisEl?.getAttribute("xyz"), [0, 0, 1]),
    });
  }
  return { robotName, links, joints };
}

function urdfParseVec3(str, fallback = [0, 0, 0]) {
  if (!str) return [...fallback];
  const parts = str.trim().split(/\s+/).map(Number);
  return [parts[0] || 0, parts[1] || 0, parts[2] || 0];
}

/**
 * Resolve a URDF mesh filename to an API URL that serves the file.
 *
 * urdfRef   e.g.  "go2_1234/urdf/go2.urdf"
 * filename  e.g.  "package://go2_description/meshes/base.stl"
 *                 or "../meshes/base.stl"
 *                 or "meshes/base.stl"
 */
function resolveUrdfMeshUrl(filename, urdfRef) {
  if (!filename || !urdfRef) return null;
  const assetName = urdfRef.split("/")[0];
  const urdfDir = urdfRef.split("/").slice(1, -1).join("/"); // e.g. "urdf"

  let subPath;
  // package://anything/sub/path.stl → sub/path.stl
  const pkgMatch = filename.match(/^package:\/\/[^/]+\/(.+)$/);
  if (pkgMatch) {
    subPath = pkgMatch[1];
  } else if (filename.startsWith("/")) {
    // Absolute URI — not resolvable; skip
    return null;
  } else {
    // Relative to the URDF file directory
    const combined = (urdfDir ? urdfDir + "/" : "") + filename;
    // Normalise ".." segments
    const parts = combined.split("/");
    const resolved = [];
    for (const part of parts) {
      if (part === "..") resolved.pop();
      else if (part && part !== ".") resolved.push(part);
    }
    subPath = resolved.join("/");
  }
  if (!subPath) return null;
  return `/api/robots/urdf/packages/${encodeURIComponent(assetName)}/files/${subPath}`;
}

function resolveUrdfMeshUrls(filename, urdfRef) {
  const primary = resolveUrdfMeshUrl(filename, urdfRef);
  const urls = primary ? [primary] : [];
  if (!filename || !urdfRef || filename.startsWith("/") || filename.startsWith("package://")) {
    return urls;
  }

  // Some CAD exporters place the URDF in urdf/ and meshes in the package root,
  // but still emit "meshes/foo.stl" instead of "../meshes/foo.stl". Keep the
  // standards-compliant relative URL first, then try the package-root path.
  const parts = [];
  for (const part of filename.replace(/\\/g, "/").split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) return urls;
      parts.pop();
    } else {
      parts.push(part);
    }
  }
  if (!parts.length) return urls;
  const assetName = urdfRef.split("/")[0];
  const fallback = `/api/robots/urdf/packages/${encodeURIComponent(assetName)}/files/${parts.join("/")}`;
  if (!urls.includes(fallback)) urls.push(fallback);
  return urls;
}

/**
 * Apply RPY (roll-pitch-yaw) Euler angles to a THREE.Object3D using
 * the URDF convention (extrinsic XYZ = Rz * Ry * Rx).
 */
function applyUrdfRpy(obj, rpy) {
  const [r, p, y] = rpy;
  obj.rotation.set(r, p, y, "XYZ");
}

/**
 * Build a Three.js kinematic chain from a parsed URDF.
 * Returns { root, jointMap } where:
 *   root     — THREE.Group for the root link (add to scene)
 *   jointMap — Map<jointName, { pivotGroup, axis, type }>
 *              pivotGroup is the group whose rotation controls that joint
 */
function buildUrdfKinematicChain(parsed) {
  const { links, joints } = parsed;

  // Create a Group per link
  const linkGroups = new Map();
  for (const [name] of links) {
    linkGroups.set(name, new THREE.Group());
    linkGroups.get(name).name = `link_${name}`;
  }

  // Build joint pivots and wire parent → child
  const jointMap = new Map();
  const childLinks = new Set();
  for (const joint of joints) {
    const parentGroup = linkGroups.get(joint.parent);
    const childGroup = linkGroups.get(joint.child);
    if (!parentGroup || !childGroup) continue;
    childLinks.add(joint.child);

    // pivotGroup sits at the joint origin inside the parent link frame
    const pivotGroup = new THREE.Group();
    pivotGroup.name = `joint_${joint.name}`;
    pivotGroup.position.set(...joint.xyz);
    applyUrdfRpy(pivotGroup, joint.rpy);

    pivotGroup.add(childGroup);
    parentGroup.add(pivotGroup);

    if (joint.type !== "fixed") {
      jointMap.set(joint.name.toLowerCase(), {
        pivotGroup,
        axis: new THREE.Vector3(...joint.axis).normalize(),
        type: joint.type,
        basePose: pivotGroup.quaternion.clone(),
      });
    }
  }

  // Find root link (no joint points to it as a child)
  const allLinkNames = Array.from(linkGroups.keys());
  const rootName = allLinkNames.find((n) => !childLinks.has(n)) || allLinkNames[0];
  const root = linkGroups.get(rootName) || new THREE.Group();
  return { root, jointMap, linkGroups };
}

/**
 * Apply joint angles (Map or plain object) to a built kinematic chain.
 * angles keys are lowercase canonical joint names, values are radians.
 */
function updateUrdfChainAngles(chain, angles) {
  if (!chain?.jointMap) return;
  for (const [name, entry] of chain.jointMap) {
    const angle = angles[name] ?? 0;
    // Restore the base pose (from joint origin rpy), then rotate around axis.
    entry.pivotGroup.quaternion.copy(entry.basePose);
    const q = new THREE.Quaternion().setFromAxisAngle(entry.axis, angle);
    entry.pivotGroup.quaternion.multiply(q);
  }
}

/**
 * Load all mesh files for a parsed URDF and attach geometries to the chain.
 * Returns a count of successfully loaded meshes.
 */
async function loadUrdfMeshes(parsed, chain, urdfRef) {
  const { links } = parsed;
  const { linkGroups } = chain;

  const meshMat = new THREE.MeshStandardMaterial({
    color: 0x94a3b8,
    roughness: 0.55,
    metalness: 0.28,
    side: THREE.DoubleSide,
  });

  let loaded = 0;
  let failed = 0;
  const fetches = [];

  for (const [linkName, link] of links) {
    const group = linkGroups.get(linkName);
    if (!group) continue;
    for (const vis of link.visual) {
      if (!vis.filename) continue;
      const meshUrls = resolveUrdfMeshUrls(vis.filename, urdfRef);
      if (!meshUrls.length) continue;

      fetches.push((async () => {
        try {
          let res = null;
          for (const meshUrl of meshUrls) {
            const candidate = await fetch(meshUrl, { credentials: "include", cache: "default" });
            if (candidate.ok) {
              res = candidate;
              break;
            }
          }
          if (!res) { failed++; return; }
          const buffer = await res.arrayBuffer();
          const ext = vis.filename.split(".").pop().toLowerCase();
          let geometry = null;
          if (ext === "stl") geometry = parseStlGeometry(buffer);
          else if (ext === "obj") geometry = parseObjGeometry(new TextDecoder().decode(buffer));
          else if (ext === "dae") geometry = parseDaeGeometry(new TextDecoder().decode(buffer));
          if (!geometry) { failed++; return; }

          // Apply mesh-level scale and origin offset
          if (vis.scale && (vis.scale[0] !== 1 || vis.scale[1] !== 1 || vis.scale[2] !== 1)) {
            geometry.scale(...vis.scale);
          }
          const mesh = new THREE.Mesh(geometry, meshMat.clone());
          mesh.position.set(...vis.xyz);
          applyUrdfRpy(mesh, vis.rpy);
          group.add(mesh);
          loaded++;
        } catch {
          failed++;
        }
      })());
    }
  }

  await Promise.allSettled(fetches);
  return { loaded, failed };
}

/**
 * Auto-scale and reposition the loaded URDF so it fits the stance viewer.
 */
function normalizeUrdfChainPose(root) {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  if (maxDim > 1e-9) {
    const targetSize = 0.6;
    const scale = targetSize / maxDim;
    root.scale.setScalar(scale);
    root.position.set(-center.x * scale, -center.y * scale, -box.min.z * scale);
  }
}

/**
 * Load the URDF for the currently-selected robot and rebuild the stance viewer
 * with real meshes.  Called from selectRobot when urdf_ref is present.
 */
async function loadUrdfIntoStanceViewer(robot, { autoOpenModal = false } = {}) {
  if (!stancePose.scene) return;
  const urdfRef = robot?.urdf_ref || "";
  if (!urdfRef) return;

  const assetName = urdfRef.split("/")[0];
  // 直接从 package 文件服务接口取 URDF，兼容 builtin 和 uploaded 两种存储方式
  const urdfSubPath = urdfRef.split("/").slice(1).join("/");
  const urdfUrl = `/api/robots/urdf/packages/${encodeURIComponent(assetName)}/files/${urdfSubPath}`;

  if (el.urdfMeshStatus) el.urdfMeshStatus.textContent = "加载 URDF mesh…";

  try {
    const res = await fetch(urdfUrl, { credentials: "include", cache: "default" });
    if (!res.ok) throw new Error(`urdf ${res.status}`);
    const xmlText = await res.text();

    const parsed = parseUrdfXml(xmlText);
    const chain = buildUrdfKinematicChain(parsed);

    // Remove old URDF chain if any, keep schematic hidden
    if (stancePose.urdfChain) {
      stancePose.scene.remove(stancePose.urdfChain.root);
      stancePose.urdfChain.root.traverse((n) => {
        n.geometry?.dispose?.();
        if (Array.isArray(n.material)) n.material.forEach((m) => m.dispose?.());
        else n.material?.dispose?.();
      });
    }
    stancePose.urdfChain = chain;

    // Hide schematic while loading meshes
    if (stancePose.schematicGroup) stancePose.schematicGroup.visible = false;

    const { loaded, failed } = await loadUrdfMeshes(parsed, chain, urdfRef);

    if (loaded > 0) {
      normalizeUrdfChainPose(chain.root);
      stancePose.scene.add(chain.root);
      // 加载完成后对准摄像机
      fitCameraToScene();
      // Apply current joint angles (re-keyed to real URDF joint names)
      const currentAngles = collectCurrentStanceAngles();
      const mapping = activeJointMapping();
      const low = {};
      for (const [slot, v] of Object.entries(currentAngles)) {
        const realName = (mapping[String(slot).toLowerCase()] || canonicalToUrdf(slot) || slot);
        low[String(realName).toLowerCase()] = v;
      }
      updateUrdfChainAngles(chain, low);
      const msg = `URDF mesh: ${loaded} 个${failed ? `（${failed} 格式不支持，建议用 STL）` : ""}`;
      if (el.urdfMeshStatus) el.urdfMeshStatus.textContent = msg;
      if (el.expandUrdfViewer) el.expandUrdfViewer.style.display = "";
      if (autoOpenModal) openUrdfModal(robot);
    } else {
      // No meshes loaded — fall back to schematic
      stancePose.urdfChain = null;
      if (stancePose.schematicGroup) stancePose.schematicGroup.visible = true;
      const daeHint = failed ? "（mesh 资源路径错误或格式不支持，请检查 URDF 引用）" : "";
      const msg = failed
        ? `mesh 加载失败 ${daeHint}`
        : "URDF 无 mesh 引用，使用示意图调整关节";
      if (el.urdfMeshStatus) el.urdfMeshStatus.textContent = msg;
      if (el.expandUrdfViewer) el.expandUrdfViewer.style.display = "";
      if (autoOpenModal) openUrdfModal(robot);
    }
  } catch {
    stancePose.urdfChain = null;
    if (stancePose.schematicGroup) stancePose.schematicGroup.visible = true;
    if (el.urdfMeshStatus) el.urdfMeshStatus.textContent = "";
    if (el.expandUrdfViewer) el.expandUrdfViewer.style.display = "";
    if (autoOpenModal) openUrdfModal(robot);
  }
}

// ── 全屏 URDF 预览模态层（独立 Three.js renderer）────────────────────────────
// 模态层拥有自己的 renderer/scene/camera，与小查看器完全隔离，
// 避免移动 canvas 导致的 WebGL context 丢失和 OrbitControls 失效问题。

const urdfModal3D = {
  renderer: null, scene: null, camera: null,
  controls: null, chain: null, animFrame: null,
};

let _modalAngles = {};

/** 打开全屏预览模态层，独立初始化 Three.js 并异步加载 URDF mesh。 */
async function openUrdfModal(robot) {
  if (!el.urdfModal) return;

  _modalAngles = { ...collectCurrentStanceAngles() };
  if (el.urdfModalTitle) el.urdfModalTitle.textContent = robot?.name || "机器人预览";
  if (el.urdfModalMeshStatus) el.urdfModalMeshStatus.textContent = "加载中…";
  renderUrdfModalJoints(_modalAngles);

  el.urdfModal.style.display = "flex";
  document.body.style.overflow = "hidden";

  // 初始化独立 renderer（确保容器已可见再创建，否则 canvas 尺寸为0）
  _initModalRenderer();
  _startModalAnimation();

  // 异步加载 URDF mesh
  if (robot?.urdf_ref) {
    await _loadUrdfForModal(robot);
  } else {
    if (el.urdfModalMeshStatus) el.urdfModalMeshStatus.textContent = "无 URDF 文件";
  }
}

/** 关闭模态层，停止渲染并释放 GPU 资源。 */
function closeUrdfModal() {
  if (!el.urdfModal) return;
  el.urdfModal.style.display = "none";
  document.body.style.overflow = "";
  _disposeModalRenderer();
}

function saveUrdfModalPose() {
  el.jointAngles.querySelectorAll('[data-role="num"]').forEach((input) => {
    const v = _modalAngles[input.dataset.slot];
    if (v !== undefined) {
      input.value = Number(v).toFixed(3);
      const range = el.jointAngles.querySelector(`[data-role="range"][data-slot="${input.dataset.slot}"]`);
      if (range) range.value = input.value;
    }
  });
  updateStancePoseAngles(_modalAngles);
  closeUrdfModal();
}

function resetUrdfModalPose() {
  const defaults = state.current?.default_joint_angles || {};
  _modalAngles = {};
  for (const slot of activeCanonicalJoints()) _modalAngles[slot] = num(defaults[slot], 0);
  renderUrdfModalJoints(_modalAngles);
  _applyModalAngles();
}

// ── 内部：初始化 / 销毁 modal renderer ─────────────────────────────────────

function _initModalRenderer() {
  const container = el.urdfModalCanvas;
  if (!container) return;

  // 清理旧 renderer（如果有）
  _disposeModalRenderer();

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070d14);

  const camera = new THREE.PerspectiveCamera(40, 1, 0.001, 100);
  camera.up.set(0, 0, 1);
  camera.position.set(1.5, -2.0, 1.0);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0.3);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;

  // 灯光
  scene.add(new THREE.HemisphereLight(0xdbeafe, 0x0f172a, 2.0));
  const key = new THREE.DirectionalLight(0xffffff, 2.8);
  key.position.set(2, -3, 4);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x334466, 1.0);
  fill.position.set(-2, 1, 2);
  scene.add(fill);

  // 地板格
  const grid = new THREE.GridHelper(2, 10, 0x1e3040, 0x0f1e28);
  grid.rotation.x = Math.PI / 2;
  scene.add(grid);

  urdfModal3D.renderer = renderer;
  urdfModal3D.scene = scene;
  urdfModal3D.camera = camera;
  urdfModal3D.controls = controls;
  urdfModal3D.chain = null;
}

function _startModalAnimation() {
  if (urdfModal3D.animFrame) return;
  const tick = () => {
    if (!urdfModal3D.renderer) return;
    urdfModal3D.animFrame = requestAnimationFrame(tick);
    // 自动追踪容器尺寸
    const container = el.urdfModalCanvas;
    if (container) {
      const w = Math.max(1, container.clientWidth);
      const h = Math.max(1, container.clientHeight);
      const size = urdfModal3D.renderer.getSize(new THREE.Vector2());
      if (Math.abs(size.x - w) > 1 || Math.abs(size.y - h) > 1) {
        urdfModal3D.renderer.setSize(w, h, false);
        urdfModal3D.camera.aspect = w / h;
        urdfModal3D.camera.updateProjectionMatrix();
      }
    }
    urdfModal3D.controls?.update();
    urdfModal3D.renderer.render(urdfModal3D.scene, urdfModal3D.camera);
  };
  tick();
}

function _disposeModalRenderer() {
  if (urdfModal3D.animFrame) {
    cancelAnimationFrame(urdfModal3D.animFrame);
    urdfModal3D.animFrame = null;
  }
  if (urdfModal3D.scene) {
    urdfModal3D.scene.traverse((obj) => {
      obj.geometry?.dispose?.();
      if (Array.isArray(obj.material)) obj.material.forEach((m) => m?.dispose?.());
      else obj.material?.dispose?.();
    });
  }
  urdfModal3D.controls?.dispose();
  if (urdfModal3D.renderer) {
    urdfModal3D.renderer.domElement.remove();
    urdfModal3D.renderer.dispose();
  }
  urdfModal3D.renderer = null;
  urdfModal3D.scene = null;
  urdfModal3D.camera = null;
  urdfModal3D.controls = null;
  urdfModal3D.chain = null;
}

// ── 内部：加载 URDF 进 modal scene ─────────────────────────────────────────

async function _loadUrdfForModal(robot) {
  const urdfRef = robot?.urdf_ref || "";
  if (!urdfRef || !urdfModal3D.scene) return;

  const assetName = urdfRef.split("/")[0];
  const urdfSubPath = urdfRef.split("/").slice(1).join("/");
  const urdfUrl = `/api/robots/urdf/packages/${encodeURIComponent(assetName)}/files/${urdfSubPath}`;

  try {
    const res = await fetch(urdfUrl, { credentials: "include", cache: "default" });
    if (!res.ok) throw new Error(`urdf fetch ${res.status}`);
    const xmlText = await res.text();

    const parsed = parseUrdfXml(xmlText);
    const chain = buildUrdfKinematicChain(parsed);
    const { loaded, failed } = await loadUrdfMeshes(parsed, chain, urdfRef);

    if (!urdfModal3D.scene) return; // 用户已关闭

    if (loaded > 0) {
      normalizeUrdfChainPose(chain.root);
      urdfModal3D.scene.add(chain.root);
      urdfModal3D.chain = chain;
      _applyModalAngles();
      _fitModalCamera(chain.root);
      if (el.urdfModalMeshStatus)
        el.urdfModalMeshStatus.textContent = `已加载 ${loaded} 个 mesh${failed ? `（${failed} 格式不支持）` : ""}`;
    } else {
      const hint = failed ? `URDF mesh 格式不支持（共 ${failed} 个），建议换用 .stl` : "URDF 无 mesh，关节仍可调整";
      if (el.urdfModalMeshStatus) el.urdfModalMeshStatus.textContent = hint;
    }
  } catch (err) {
    if (el.urdfModalMeshStatus) el.urdfModalMeshStatus.textContent = `加载失败：${err.message}`;
  }
}

function _applyModalAngles() {
  if (!urdfModal3D.chain) return;
  // _modalAngles is keyed by canonical slots (fl_hip_joint …). Translate each
  // slot to the robot's REAL URDF joint name via the saved joint mapping, so
  // the slider drives the correct joint even when the URDF uses different names
  // (e.g. ABAD/HIP/KNEE). Falls back to the canonical name when unmapped.
  const mapping = activeJointMapping();
  const low = {};
  for (const [slot, v] of Object.entries(_modalAngles)) {
    const canonical = String(slot).toLowerCase();
    const realName = (mapping[canonical] || canonicalToUrdf(canonical) || canonical);
    low[String(realName).toLowerCase()] = num(v, 0);
  }
  updateUrdfChainAngles(urdfModal3D.chain, low);
}

function _fitModalCamera(root) {
  if (!urdfModal3D.camera || !urdfModal3D.controls) return;
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size   = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 0.1);
  const dist   = maxDim * 2.5;
  urdfModal3D.camera.position.set(center.x + dist * 0.6, center.y - dist * 0.8, center.z + dist * 0.6);
  urdfModal3D.camera.near = dist * 0.01;
  urdfModal3D.camera.far  = dist * 20;
  urdfModal3D.camera.updateProjectionMatrix();
  urdfModal3D.controls.target.copy(center);
  urdfModal3D.controls.update();
}

// ── 关节滑块渲染 ────────────────────────────────────────────────────────────

function renderUrdfModalJoints(angles) {
  if (!el.urdfModalJoints) return;
  const low = {};
  for (const [k, v] of Object.entries(angles || {})) low[String(k).toLowerCase()] = num(v, 0);
  const limits = normalizedJointLimits();
  el.urdfModalJoints.innerHTML = "";

  for (const leg of LEGS) {
    const section = document.createElement("div");
    section.className = "urdf-modal-leg";
    section.innerHTML = `<div class="urdf-modal-leg-title">${LEG_LABEL[leg]}</div>`;

    for (const seg of activeSegments()) {
      const slot = `${leg}_${seg}_joint`;
      const value = low[slot] ?? 0;
      const [lo, hi] = jointRange(slot, value, limits);

      const row = document.createElement("div");
      row.className = "urdf-modal-joint-row";
      row.innerHTML = `
        <span>${seg}</span>
        <input type="range" min="${lo}" max="${hi}" step="0.01" value="${value}" data-slot="${slot}" />
        <input type="number" min="${lo}" max="${hi}" step="any" inputmode="decimal" value="${value.toFixed(3)}" data-slot="${slot}" />`;

      const rangeEl = row.querySelector("input[type=range]");
      const numEl   = row.querySelector("input[type=number]");
      const sync = () => {
        const v2 = num(rangeEl.value, 0);
        numEl.value = v2.toFixed(3);
        _modalAngles[slot] = v2;
        _applyModalAngles();
      };
      const syncNum = () => {
        const v2 = num(numEl.value, 0);
        rangeEl.value = String(v2);
        _modalAngles[slot] = v2;
        _applyModalAngles();
      };
      rangeEl.addEventListener("input", sync);
      numEl.addEventListener("input", syncNum);
      section.appendChild(row);
    }
    el.urdfModalJoints.appendChild(section);
  }
}

/** resize stancePose renderer 到指定容器的尺寸。*/
function resizeStancePoseToContainer(container) {
  if (!stancePose.renderer || !container) return;
  const w = Math.max(1, Math.round(container.clientWidth  || container.offsetWidth  || 1));
  const h = Math.max(1, Math.round(container.clientHeight || container.offsetHeight || 1));
  stancePose.renderer.setSize(w, h, false);
  if (stancePose.camera) {
    stancePose.camera.aspect = w / h;
    stancePose.camera.updateProjectionMatrix();
  }
}

/**
 * 把摄像机对准场景中可见内容的包围盒。
 * 跳过地板格（GridHelper）和示意图组（当 URDF 已加载时）。
 */
function fitCameraToScene() {
  if (!stancePose.scene || !stancePose.camera || !stancePose.controls) return;
  const box = new THREE.Box3();
  stancePose.scene.traverse((obj) => {
    if (!obj.isMesh) return;
    // 跳过地板格网格
    if (obj.parent?.isGridHelper || obj.geometry?.type === "PlaneGeometry") return;
    // 如果有真实 URDF chain，跳过示意图
    if (stancePose.urdfChain && stancePose.schematicGroup?.children.includes(obj)) return;
    const objBox = new THREE.Box3().setFromObject(obj);
    if (!objBox.isEmpty()) box.union(objBox);
  });
  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size   = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 0.1);

  // 把摄像机放在场景中心的前上方，距离 = maxDim × 2
  const dist = maxDim * 2.2;
  stancePose.camera.position.set(
    center.x + dist * 0.55,
    center.y - dist * 0.75,
    center.z + dist * 0.55,
  );
  stancePose.camera.near = dist * 0.01;
  stancePose.camera.far  = dist * 10;
  stancePose.camera.updateProjectionMatrix();
  stancePose.controls.target.copy(center);
  stancePose.controls.update();
}

function renderStepResult(result) {
  const warnings = (result.warnings || []).map((w) => `<div class="step-warning">${escapeHtml(w)}</div>`).join("");
  const detected = (result.detected_parts || []).slice(0, 10).map((name) => `<span>${escapeHtml(name)}</span>`).join("");
  const conversion = result.conversion || {};
  const robotLink = result.robot_id
    ? `<a class="btn" href="/robots/?robot=${encodeURIComponent(result.robot_id)}">打开机器人配置</a>`
    : "";
  el.stepResult.innerHTML = `
    <div class="step-result-head">
      <strong>${escapeHtml(result.robot_name)}</strong>
      <span>${escapeHtml(result.asset_name)}</span>
    </div>
    <div class="step-result-actions">
      <a class="primary" href="${escapeHtml(result.download_url)}">下载 package zip</a>
      <a class="btn" href="${escapeHtml(result.urdf_url)}" target="_blank" rel="noreferrer">查看 URDF</a>
      ${robotLink}
    </div>
    <div class="step-meta">
      <span>mesh: ${escapeHtml(result.mesh_ref || "")}</span>
      <span>material: ${escapeHtml(conversion.material || "")}</span>
      <span>mass: ${formatMass(conversion.computed_mass_kg)}</span>
      <span>inertial links: ${Number(conversion.computed_inertial_links || 0)}</span>
      <span>linked parts: ${Number(conversion.linked_meshes || 0)}</span>
      <span>converter: ${escapeHtml(conversion.tool || "none")}</span>
    </div>
    ${detected ? `<div class="step-detected"><b>folder files</b>${detected}</div>` : ""}
    ${warnings}`;
}

async function loadList() {
  try {
    state.list = await robots.list();
  } catch (err) {
    state.list = [];
    el.editorStatus.textContent = err instanceof ApiError ? err.message : "加载失败";
  }
  el.robotCount.textContent = String(state.list.length);
  renderList();
}

function renderList() {
  el.robotList.innerHTML = "";
  // 检测重复名（大小写不敏感）
  const nameCounts = new Map();
  for (const r of state.list) {
    const k = r.name.trim().toLowerCase();
    nameCounts.set(k, (nameCounts.get(k) || 0) + 1);
  }

  for (const r of state.list) {
    const isDup = (nameCounts.get(r.name.trim().toLowerCase()) || 1) > 1;
    const isBuiltin = r.source === "builtin";
    const sourceLabel = isBuiltin ? "内置模板" : "我的机器人";
    const li = document.createElement("li");
    li.className = "robot-item" + (r.id === state.selectedId ? " active" : "");
    li.innerHTML = `
      <span class="r-mark">${escapeHtml((r.name || "?").slice(0, 2).toUpperCase())}</span>
      <span class="r-body">
        <span class="r-title">${escapeHtml(r.name || r.id)}${isDup ? ' <span class="r-dup-badge">重复</span>' : ""}</span>
        <span class="r-sub">${sourceLabel} · ${escapeHtml(r.vendor || r.morphology || "")}</span>
      </span>
      ${isBuiltin ? "" : `<button class="r-delete-btn btn" type="button" title="删除此机器人" data-id="${escapeAttr(r.id)}">✕</button>`}`;
    li.querySelector(".r-delete-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      onDeleteRobot(r);
    });
    li.addEventListener("click", () => selectRobot(r.id));
    el.robotList.append(li);
  }
}

async function selectRobot(id, { autoOpenModal = false } = {}) {
  state.selectedId = id;
  renderList();
  el.form.style.display = "none";
  el.editorStatus.textContent = "加载中";
  el.saveHint.textContent = "";
  el.formError.textContent = "";
  if (el.expandUrdfViewer) el.expandUrdfViewer.style.display = "none";
  if (el.urdfMeshStatus) el.urdfMeshStatus.textContent = "";
  let robot;
  try {
    robot = await robots.get(id);
  } catch (err) {
    el.editorStatus.textContent = err instanceof ApiError ? err.message : "加载失败";
    return;
  }
  state.current = robot;
  el.editorTitle.textContent = robot.name || robot.id;
  el.editorSub.textContent = `${robot.source === "builtin" ? "内置模板" : "我的机器人"} / ${robot.morphology || ""}`;
  el.editorStatus.textContent = "已加载保存配置";
  prefillForm(robot);
  el.form.style.display = "flex";
  initStancePoseViewer();
  updateStancePoseAngles(robot.default_joint_angles || {});
  // 有 URDF：小预览用真实 mesh 渲染（loadUrdfIntoStanceViewer 内部加载 mesh，
  // 失败自动回退示意图）。不传 autoOpenModal，避免它直接弹角度——上传新机器人时
  // 仍先停在映射表格让用户核对/修正，核对保存后自己点“展开预览”调整角度。
  if (robot.urdf_ref) {
    if (el.expandUrdfViewer) el.expandUrdfViewer.style.display = "";
    loadUrdfIntoStanceViewer(robot);   // async，小预览显示真实 mesh
    if (autoOpenModal) {
      if (el.jointOrderTable) {
        el.jointOrderTable.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      if (el.jointOrderStatus) {
        el.jointOrderStatus.textContent =
          "① 请核对每个关节槽位对应的 URDF 关节（系统已按顺序预填，可能需要修正）→ ② 保存 → ③ 点“展开预览”调整角度";
        el.jointOrderStatus.classList.add("bad");
      }
      el.editorStatus.textContent = "新机器人：请先核对关节映射";
    }
  }
}

function prefillForm(robot) {
  el.fName.value = robot.name || "";
  el.fVendor.value = robot.vendor || "";

  renderJointOrder(robot.joint_order || []);
  renderJointAngles(robot.default_joint_angles || {});

  const ctrl = robot.control_defaults || {};
  const stiff = ctrl.stiffness || {};
  const damp = ctrl.damping || {};
  const wheelLeg = isWheelLegMorphology(robot.morphology);
  setWheelControlVisibility(wheelLeg);
  el.kpHip.value = num(stiff.hip, 30);
  el.kpThigh.value = num(stiff.thigh, 30);
  el.kpCalf.value = num(stiff.calf, 30);
  el.kpWheel.value = num(stiff.wheel, 0);
  el.kdHip.value = num(damp.hip, 0.5);
  el.kdThigh.value = num(damp.thigh, 0.5);
  el.kdCalf.value = num(damp.calf, 0.5);
  el.kdWheel.value = num(damp.wheel, 1.0);
  el.actionScale.value = num(ctrl.action_scale, 0.25);
  el.decimation.value = num(ctrl.decimation, 4);
  el.baseHeightTarget.value = num(ctrl.base_height_target ?? 0.45, 0.45);
  const envelopes = ctrl.motor_envelopes || {};
  el.envelopeHip.value = formatMotorEnvelope(envelopes.hip);
  el.envelopeThigh.value = formatMotorEnvelope(envelopes.thigh);
  el.envelopeCalf.value = formatMotorEnvelope(envelopes.calf);
  el.envelopeWheel.value = formatMotorEnvelope(envelopes.wheel);
  el.saveButton.textContent = robot.source === "builtin" ? "保存到我的机器人" : "保存配置";
  el.saveHint.textContent = robot.source === "builtin" ? "修改会保存为您的私有副本，不影响其他用户。" : "";
}

function renderJointOrder(order) {
  const canonicalJoints = activeCanonicalJoints();
  const choices = uniqueJointChoices(order);
  const mapping = mappingBySlot(order);
  let html = `<div class="jo-head">canonical slot</div><div class="jo-head">URDF joint</div>`;
  for (const slot of canonicalJoints) {
    const selected = mapping[slot] || canonicalToUrdf(slot);
    if (selected && !choices.some((choice) => choice.toLowerCase() === selected.toLowerCase())) {
      choices.push(selected);
    }
    const options = [
      `<option value="">未选择</option>`,
      ...choices.map((joint) => `<option value="${escapeHtml(joint)}"${joint === selected ? " selected" : ""}>${escapeHtml(joint)}</option>`),
    ].join("");
    html += `
      <label class="jo-canonical" for="map_${slot}">${slot}</label>
      <select id="map_${slot}" class="field jo-select" data-slot="${slot}">${options}</select>`;
  }
  el.jointOrderTable.innerHTML = html;
  el.jointOrderTable.querySelectorAll("select[data-slot]").forEach((select) => {
    select.addEventListener("change", () => validateJointOrder());
  });
  validateJointOrder();
}

function uniqueJointChoices(order) {
  const choices = [];
  const seen = new Set();
  const add = (name) => {
    const value = String(name || "").trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return;
    seen.add(key);
    choices.push(value);
  };
  for (const joint of order || []) add(joint);
  for (const slot of activeCanonicalJoints()) add(canonicalToUrdf(slot));
  return choices;
}

function currentJointChoices() {
  return uniqueJointChoices(state.current?.joint_order || jointOrderValues());
}

function canonicalToUrdf(slot) {
  const [leg, segment] = slot.split("_");
  return `${leg.toUpperCase()}_${segment}_joint`;
}

/**
 * Return the authoritative canonical-slot → real-URDF-joint mapping.
 * Prefers the LIVE joint-order table (reflects unsaved edits); falls back to
 * the saved robot.joint_order. Null-safe: never throws if the table is absent.
 * NOTE: an empty array is treated as "no mapping" (not a truthy short-circuit).
 */
function activeJointMapping() {
  let order = [];
  try {
    const live = jointOrderValues();
    if (Array.isArray(live) && live.some((v) => v)) order = live;
  } catch { /* table not in DOM on this view — ignore */ }
  if (!order.length) {
    const saved = state.current?.joint_order;
    if (Array.isArray(saved) && saved.length) order = saved;
  }
  return mappingBySlot(order);
}

function mappingBySlot(order) {
  const canonicalJoints = activeCanonicalJoints();
  const mapping = {};
  const list = Array.isArray(order) ? order : [];
  if (list.length === canonicalJoints.length) {
    canonicalJoints.forEach((slot, index) => {
      mapping[slot] = String(list[index] || "").trim();
    });
    return mapping;
  }
  for (const real of list) {
    const canonical = String(real || "").trim().toLowerCase();
    if (canonicalJoints.includes(canonical)) mapping[canonical] = real;
  }
  return mapping;
}

function jointOrderValues() {
  return Array.from(el.jointOrderTable.querySelectorAll("select[data-slot]"))
    .map((select) => select.value.trim());
}

function validateJointOrder() {
  const canonicalJoints = activeCanonicalJoints();
  const selects = Array.from(el.jointOrderTable.querySelectorAll("select[data-slot]"));
  const values = selects.map((select) => select.value.trim());
  const counts = new Map();
  for (const value of values) {
    if (!value) continue;
    const key = value.toLowerCase();
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const duplicates = new Set([...counts.entries()].filter(([, count]) => count > 1).map(([key]) => key));
  const missing = values.filter((value) => !value).length;
  selects.forEach((select) => {
    const key = select.value.trim().toLowerCase();
    select.classList.toggle("invalid", !key || duplicates.has(key));
  });

  let message = `映射完整：${values.length}/${canonicalJoints.length}`;
  let ok = true;
  if (missing) {
    ok = false;
    message = `还有 ${missing} 个 slot 未选择 URDF joint`;
  } else if (duplicates.size) {
    ok = false;
    message = `重复选择：${[...duplicates].join(", ")}`;
  }
  el.jointOrderStatus.textContent = message;
  el.jointOrderStatus.classList.toggle("ok", ok);
  el.jointOrderStatus.classList.toggle("bad", !ok);
  return { ok, message, values };
}

function setJointOrderValues(values) {
  const selects = Array.from(el.jointOrderTable.querySelectorAll("select[data-slot]"));
  selects.forEach((select, index) => {
    const value = values[index] || "";
    if (value && !Array.from(select.options).some((option) => option.value.toLowerCase() === value.toLowerCase())) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.append(option);
    }
    select.value = value;
  });
}

function applyJointMapping(mode) {
  const canonicalJoints = activeCanonicalJoints();
  const choices = currentJointChoices();
  if (mode === "clear") {
    setJointOrderValues(canonicalJoints.map(() => ""));
    const result = validateJointOrder();
    el.jointOrderStatus.textContent = `${result.message}；可以逐行从右侧下拉选择真实 URDF joint`;
    return;
  }
  if (mode === "order") {
    const values = canonicalJoints.map((_, index) => choices[index] || "");
    setJointOrderValues(values);
    const result = validateJointOrder();
    el.jointOrderStatus.textContent = `${result.message}；已按候选列表前 ${canonicalJoints.length} 个关节填入`;
    return;
  }
  const used = new Set();
  const values = canonicalJoints.map((slot) => {
    const match = autoJointForSlot(slot, choices, used);
    if (match) used.add(match.toLowerCase());
    return match;
  });
  setJointOrderValues(values);
  const result = validateJointOrder();
  const matched = values.filter(Boolean).length;
  el.jointOrderStatus.textContent = result.ok
    ? `按名称自动匹配完成：${matched}/${canonicalJoints.length}，确认后保存配置`
    : `按名称匹配到 ${matched}/${canonicalJoints.length}，剩余行请手动选择`;
}

function autoJointForSlot(slot, choices, used) {
  const [leg, segment] = slot.split("_");
  let best = "";
  let bestScore = 0;
  for (const joint of choices) {
    const key = joint.toLowerCase();
    if (used.has(key)) continue;
    const score = jointLegScore(joint, leg) + jointSegmentScore(joint, segment);
    if (score > bestScore) {
      best = joint;
      bestScore = score;
    }
  }
  return bestScore >= 4 ? best : "";
}

function jointLegScore(name, leg) {
  const n = `_${normalizeName(name)}_`;
  const aliases = {
    fl: ["_fl_", "_lf_", "_f_l_", "_front_l_", "_left_front_"],
    fr: ["_fr_", "_rf_", "_ft_", "_f_r_", "_front_r_", "_right_front_"],
    rl: ["_rl_", "_lr_", "_r_l_", "_rear_l_", "_left_rear_", "_hind_l_"],
    rr: ["_rr_", "_r_r_", "_rear_r_", "_right_rear_", "_hind_r_"],
  };
  return (aliases[leg] || []).some((alias) => n.includes(alias)) ? 2 : 0;
}

function jointSegmentScore(name, segment) {
  const n = `_${normalizeName(name)}_`;
  const aliases = {
    hip: ["_hip_", "_abad_", "_haa_"],
    thigh: ["_thigh_", "_upper_", "_hfe_"],
    calf: ["_calf_", "_shank_", "_lower_", "_knee_", "_kfe_"],
    wheel: ["_wheel_", "_foot_"],
  };
  return (aliases[segment] || []).some((alias) => n.includes(alias)) ? 2 : 0;
}

function normalizedJointLimits(limits = state.current?.joint_limits) {
  const normalized = {};
  for (const [key, value] of Object.entries(limits || {})) {
    normalized[String(key).toLowerCase()] = value || {};
  }
  return normalized;
}

function formatMotorEnvelope(points) {
  if (!Array.isArray(points)) return "";
  return points.map((point) => {
    const rpm = Array.isArray(point) ? point[0] : point?.rpm;
    const torque = Array.isArray(point) ? point[1] : point?.torque;
    return `${Number(rpm)}:${Number(torque)}`;
  }).join(", ");
}

function parseMotorEnvelope(value, role) {
  const tokens = String(value || "").split(/[,;]+/).map((item) => item.trim()).filter(Boolean);
  if (tokens.length < 2) throw new Error(`${role} 包络至少需要两个点`);
  const points = tokens.map((token) => {
    const parts = token.split(":").map((item) => Number(item.trim()));
    if (parts.length !== 2 || !parts.every(Number.isFinite) || parts.some((item) => item < 0)) {
      throw new Error(`${role} 包络格式无效`);
    }
    return { rpm: parts[0], torque: parts[1] };
  });
  if (points.some((point, index) => index > 0 && point.rpm <= points[index - 1].rpm)) {
    throw new Error(`${role} 的 rpm 必须严格递增`);
  }
  return points;
}

function jointRange(slot, value, limits = normalizedJointLimits()) {
  const limit = limits[String(slot).toLowerCase()] || {};
  const lower = Number(limit.lower);
  const upper = Number(limit.upper);
  const span = upper - lower;
  // Wheel URDFs often encode continuous rotation as +/-9999. Keep those exact
  // values in platform metadata, but use a practical range in the pose editor.
  if (Number.isFinite(lower) && Number.isFinite(upper) && lower < upper && span <= 4 * Math.PI) {
    return [lower, upper];
  }
  const segment = String(slot).split("_")[1];
  const [baseLo, baseHi] = SEG_RANGE[segment] || [-Math.PI, Math.PI];
  return [
    Math.min(baseLo, Math.floor((value - 0.2) * 100) / 100),
    Math.max(baseHi, Math.ceil((value + 0.2) * 100) / 100),
  ];
}

function renderJointAngles(angles) {
  const lowered = {};
  for (const [k, v] of Object.entries(angles)) lowered[String(k).toLowerCase()] = v;
  const limits = normalizedJointLimits();
  el.jointAngles.innerHTML = "";
  for (const leg of LEGS) {
    const group = document.createElement("div");
    group.className = "leg-group";
    group.innerHTML = `<h3>${LEG_LABEL[leg]}</h3>`;
    for (const seg of activeSegments()) {
      const slot = `${leg}_${seg}_joint`;
      const value = num(lowered[slot], 0);
      const [lo, hi] = jointRange(slot, value, limits);
      const row = document.createElement("div");
      row.className = "joint-control";
      row.innerHTML = `
        <span>${seg}</span>
        <input type="range" min="${lo}" max="${hi}" step="0.01" value="${value}" data-slot="${slot}" data-role="range" />
        <input type="number" min="${lo}" max="${hi}" step="any" inputmode="decimal" value="${value}" data-slot="${slot}" data-role="num" />`;
      const range = row.querySelector('[data-role="range"]');
      const numEl = row.querySelector('[data-role="num"]');
      range.addEventListener("input", () => { numEl.value = range.value; });
      numEl.addEventListener("input", () => { range.value = numEl.value; });
      group.append(row);
    }
    el.jointAngles.append(group);
  }
}

function resetStandingPose() {
  if (!state.current) return;
  renderJointAngles(state.current.default_joint_angles || {});
  updateStancePoseAngles(state.current.default_joint_angles || {});
}

function collectPayload() {
  const default_joint_angles = {};
  el.jointAngles.querySelectorAll('[data-role="num"]').forEach((input) => {
    default_joint_angles[input.dataset.slot] = num(input.value, 0);
  });

  const currentControl = state.current?.control_defaults || {};
  const stiffness = {
    ...(currentControl.stiffness || {}),
    hip: num(el.kpHip.value, 30),
    thigh: num(el.kpThigh.value, 30),
    calf: num(el.kpCalf.value, 30),
  };
  const damping = {
    ...(currentControl.damping || {}),
    hip: num(el.kdHip.value, 0.5),
    thigh: num(el.kdThigh.value, 0.5),
    calf: num(el.kdCalf.value, 0.5),
  };
  if (isWheelLegMorphology()) {
    stiffness.wheel = num(el.kpWheel.value, 0);
    damping.wheel = num(el.kdWheel.value, 1.0);
  }

  const controlDefaults = {
    ...currentControl,
    stiffness,
    damping,
    action_scale: num(el.actionScale.value, 0.25),
    decimation: Math.max(1, Math.round(num(el.decimation.value, 4))),
  };
  if (isWheelLegMorphology()) {
    controlDefaults.base_height_target = Math.min(1.5, Math.max(0.1, num(el.baseHeightTarget.value, 0.45)));
  }
  const envelopeInputs = {
    hip: el.envelopeHip.value,
    thigh: el.envelopeThigh.value,
    calf: el.envelopeCalf.value,
    ...(isWheelLegMorphology() ? { wheel: el.envelopeWheel.value } : {}),
  };
  const configuredRoles = Object.entries(envelopeInputs).filter(([, value]) => String(value).trim());
  if (configuredRoles.length && configuredRoles.length !== Object.keys(envelopeInputs).length) {
    const required = isWheelLegMorphology() ? "hip、thigh、calf 和 foot" : "hip、thigh 和 calf";
    throw new Error(`启用电机包络时需要填写 ${required} 曲线`);
  }
  controlDefaults.motor_envelopes = Object.fromEntries(
    configuredRoles.map(([role, value]) => [role, parseMotorEnvelope(value, role)]),
  );

  return {
    name: el.fName.value.trim(),
    vendor: el.fVendor.value.trim(),
    morphology: state.current?.morphology || QUADRUPED_MORPHOLOGY,
    joint_order: jointOrderValues(),
    default_joint_angles,
    control_defaults: controlDefaults,
  };
}

async function onSave(e) {
  e.preventDefault();
  if (!state.selectedId) return;
  el.formError.textContent = "";
  el.saveHint.textContent = "";
  el.saveButton.disabled = true;
  let payload;
  try {
    payload = collectPayload();
  } catch (error) {
    el.formError.textContent = error?.message || "电机包络配置无效";
    el.saveButton.disabled = false;
    return;
  }
  if (!payload.name) {
    el.formError.textContent = "名称不能为空";
    el.saveButton.disabled = false;
    return;
  }
  const mapping = validateJointOrder();
  if (!mapping.ok) {
    el.formError.textContent = mapping.message;
    el.saveButton.disabled = false;
    return;
  }
  try {
    const previousId = state.selectedId;
    const updated = await robots.update(state.selectedId, payload);
    state.selectedId = updated.id;
    state.current = updated;
    prefillForm(updated);
    const idx = state.list.findIndex((r) => r.id === updated.id);
    if (idx >= 0) state.list[idx] = updated;
    else state.list.push(updated);
    el.editorTitle.textContent = updated.name || updated.id;
    el.editorSub.textContent = `我的机器人 / ${updated.morphology || ""}`;
    renderList();
    el.saveHint.textContent = previousId === updated.id ? "已保存" : "已保存到“我的机器人”";
  } catch (err) {
    el.formError.textContent = err instanceof ApiError ? err.message : "保存失败";
  } finally {
    el.saveButton.disabled = false;
  }
}

function vecText(values) {
  return (values || [0, 0, 0]).map((v) => Number(v).toFixed(3).replace(/\.?0+$/, "")).join(" ");
}

function parseVec(value) {
  const out = String(value || "").replace(/,/g, " ").split(/\s+/).filter(Boolean).slice(0, 3).map((v) => num(v, 0));
  while (out.length < 3) out.push(0);
  return out;
}

async function onDeleteRobot(robot) {
  const confirmed = window.confirm(`确认删除「${robot.name}」（${robot.id}）？\n此操作不可撤销。`);
  if (!confirmed) return;
  try {
    await robots.delete(robot.id);
    if (state.selectedId === robot.id) {
      state.selectedId = null;
      state.current = null;
      el.form.style.display = "none";
      el.editorTitle.textContent = "未选择机器人";
      el.editorSub.textContent = "从左侧选择一个机器人开始编辑";
      el.editorStatus.textContent = "-";
    }
    await loadList();
  } catch (err) {
    alert(err instanceof ApiError ? err.message : "删除失败");
  }
}

async function onDeduplicateRobots() {
  const dups = state.list.filter((r) => r.source !== "builtin");
  const nameCount = new Map();
  for (const r of dups) {
    const k = r.name.trim().toLowerCase();
    nameCount.set(k, (nameCount.get(k) || 0) + 1);
  }
  const dupNames = [...nameCount.entries()].filter(([, c]) => c > 1).map(([k]) => k);
  if (!dupNames.length) {
    alert("没有找到重复的机器人。");
    return;
  }
  const confirmed = window.confirm(
    `以下名称有重复，将保留每组最新的一个，删除其余：\n${dupNames.join("、")}\n\n确认继续？`
  );
  if (!confirmed) return;
  if (el.deduplicateRobots) el.deduplicateRobots.disabled = true;
  try {
    const result = await robots.deduplicate();
    await loadList();
    // 如果当前选中的被删了，重置面板
    if (state.selectedId && result.deleted?.includes(state.selectedId)) {
      state.selectedId = null;
      state.current = null;
      el.form.style.display = "none";
      el.editorTitle.textContent = "未选择机器人";
      el.editorSub.textContent = "从左侧选择一个机器人开始编辑";
      el.editorStatus.textContent = "-";
    }
    alert(`已清理 ${result.count} 个重复机器人。`);
  } catch (err) {
    alert(err instanceof ApiError ? err.message : "清理失败");
  } finally {
    if (el.deduplicateRobots) el.deduplicateRobots.disabled = false;
  }
}

function fileExt(name) {
  const match = String(name || "").toLowerCase().match(/\.[^.]+$/);
  return match ? match[0] : "";
}

function formatBytes(value) {
  const n = Number(value) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatMass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "未计算";
  if (n < 0.001) return `${(n * 1e6).toFixed(2)} mg`;
  if (n < 1) return `${(n * 1000).toFixed(2)} g`;
  return `${n.toFixed(3)} kg`;
}

function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function escapeAttr(s) {
  return String(s).replace(/[&"'<>]/g, (c) =>
    ({ "&": "&amp;", '"': "&quot;", "'": "&#39;", "<": "&lt;", ">": "&gt;" }[c]));
}

function cadUnitScale(unit) {
  return CAD_UNIT_SCALE[String(unit || "mm").toLowerCase()] || 1;
}

function syncInputMode() {
  if (!el.stepInputMode || !el.stepFile) return;
  const assembly = (el.stepInputMode.value || "assembly") === "assembly";
  state.inputMode = assembly ? "assembly" : "folder";
  if (assembly) {
    el.stepFile.multiple = false;
    el.stepFile.removeAttribute("webkitdirectory");
    el.stepFile.removeAttribute("directory");
    el.stepFile.accept = ".stp,.step";
    if (!state.currentAssemblyId && !state.parts.length) {
      el.stepFileName.textContent = "单 STEP 模式：选择一个 .stp / .step 文件";
    }
  } else {
    el.stepFile.multiple = true;
    el.stepFile.setAttribute("webkitdirectory", "");
    el.stepFile.setAttribute("directory", "");
    el.stepFile.accept = ".stp,.step,.stl,.dae,.obj";
    if (!state.parts.length) {
      el.stepFileName.textContent = "文件夹模式：选择整机零件目录";
    }
  }
  updatePreviewStatus();
}

function previewCacheKey(part) {
  const center = Array.isArray(part.center) ? part.center.join(",") : "";
  return `${part.path}:${part.size}:${part.file?.lastModified || 0}:${part.previewScale || 1}:${part.meshUrl || ""}:${center}`;
}

function resolvePartMeshUrl(part) {
  if (part.meshUrl) return part.meshUrl;
  if (state.currentAssemblyId && part.meshName) {
    return `/api/robots/urdf/assemblies/${encodeURIComponent(state.currentAssemblyId)}/meshes/${encodeURIComponent(part.meshName)}`;
  }
  return "";
}

function resolveAssemblyPreviewUrl() {
  return state.assemblyPreviewUrl || "";
}

function normalizePreviewGeometry(geometry, scaleFactor = 1) {
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  if (!box || box.isEmpty()) return geometry;
  const center = box.getCenter(new THREE.Vector3());
  geometry.translate(-center.x, -center.y, -center.z);
  if (scaleFactor && Math.abs(scaleFactor - 1) > 1e-9) {
    geometry.scale(scaleFactor, scaleFactor, scaleFactor);
  }
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function normalizePreviewGeometryKeepPose(geometry, scaleFactor = 1) {
  geometry.computeBoundingBox();
  if (scaleFactor && Math.abs(scaleFactor - 1) > 1e-9) {
    geometry.scale(scaleFactor, scaleFactor, scaleFactor);
  }
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function combineBoundingBoxes(items) {
  const boxes = (items || [])
    .map((item) => Array.isArray(item?.bbox) ? item.bbox : item)
    .filter((bbox) => Array.isArray(bbox) && bbox.length === 6 && bbox.every((v) => Number.isFinite(Number(v))));
  if (!boxes.length) return null;
  const mins = [Infinity, Infinity, Infinity];
  const maxs = [-Infinity, -Infinity, -Infinity];
  for (const bbox of boxes) {
    mins[0] = Math.min(mins[0], Number(bbox[0]));
    mins[1] = Math.min(mins[1], Number(bbox[1]));
    mins[2] = Math.min(mins[2], Number(bbox[2]));
    maxs[0] = Math.max(maxs[0], Number(bbox[3]));
    maxs[1] = Math.max(maxs[1], Number(bbox[4]));
    maxs[2] = Math.max(maxs[2], Number(bbox[5]));
  }
  return [mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2]];
}

function assemblyProxyGeometry(part, index) {
  const scale = part.previewScale || 1;
  const bbox = Array.isArray(part.bbox) && part.bbox.length === 6 ? part.bbox : null;
  if (bbox) {
    const sx = Math.max(0.02, Math.abs(Number(bbox[3]) - Number(bbox[0])) * scale);
    const sy = Math.max(0.02, Math.abs(Number(bbox[4]) - Number(bbox[1])) * scale);
    const sz = Math.max(0.02, Math.abs(Number(bbox[5]) - Number(bbox[2])) * scale);
    const geometry = new THREE.BoxGeometry(sx, sy, sz);
    const center = Array.isArray(part.center) && part.center.length >= 3 ? part.center : [0, 0, 0];
    geometry.translate(
      Number(center[0] || 0) * scale,
      Number(center[1] || 0) * scale,
      Number(center[2] || 0) * scale,
    );
    return geometry;
  }
  return placeholderGeometry(part, index);
}

function buildPartState(file, index) {
  const path = file.webkitRelativePath || file.name;
  const row = Math.floor(index / 5);
  const col = index % 5;
  return {
    id: `part_${index}_${Math.random().toString(16).slice(2)}`,
    file,
    path,
    name: file.name,
    ext: fileExt(file.name),
    size: file.size,
    link: "",
    xyz: [Number(((col - 2) * 0.18).toFixed(3)), Number((row * 0.13).toFixed(3)), 0],
    rpy: [0, 0, 0],
    visual: true,
    collision: true,
    previewStatus: "pending",
    previewMessage: fileExt(file.name) === ".dae" ? "DAE package export only" : "",
    previewGeometry: null,
    previewPromise: null,
    meshUrl: "",
    previewScale: cadUnitScale(el.stepUnit?.value || "mm"),
  };
}

function renderAssembly() {
  renderPartList();
  renderAssignmentList();
  renderPartPreview();
  renderJointMarkers();
  updateFlowStep();
  updatePreviewStatus();
  updateAssemblySelectionPanel();
  const linked = state.parts.filter((p) => p.link).length;
  el.assemblyViewerLabel.textContent = state.parts.length
    ? `${state.parts.length} 个零件 / ${linked} 个已分配`
    : "等待选择文件";
}

function onStepFilePicked() {
  const files = Array.from(el.stepFile.files || []);
  el.stepError.textContent = "";
  el.stepResult.innerHTML = "";
  if (state.stepInspectAbort) {
    state.stepInspectAbort.abort();
    state.stepInspectAbort = null;
  }
  if (!files.length) {
    state.parts = [];
    state.solids = [];
    state.currentAssemblyId = "";
    state.selectedPartId = "";
    state.assemblyPreviewUrl = "";
    state.assemblyPreviewGeometry?.dispose?.();
    state.assemblyPreviewGeometry = null;
    state.assemblyPreviewPromise = null;
    state.assemblyBounds = null;
    syncInputMode();
    renderAssembly();
    return;
  }

  const mode = el.stepInputMode?.value || state.inputMode || "assembly";
  state.inputMode = mode;
  syncInputMode();

  if (mode === "assembly") {
    if (files.length !== 1 || ![".stp", ".step"].includes(fileExt(files[0].name))) {
      el.stepError.textContent = "单 STEP 模式只接受一个 .stp / .step 文件";
      return;
    }
    inspectSingleStep(files[0]);
    return;
  }

  const supported = files.filter((file) => CAD_MESH_EXTS.has(fileExt(file.name)));
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const folder = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : files[0].name;
  el.stepFileName.textContent = `${folder} / ${supported.length}/${files.length} CAD 文件 / ${formatBytes(totalBytes)}`;
  if (!el.stepRobotName.value.trim()) {
    el.stepRobotName.value = folder.replace(/\.(stp|step|stl|dae|obj)$/i, "").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  }
  state.currentAssemblyId = "";
  state.assemblyPreviewUrl = "";
  state.assemblyPreviewGeometry?.dispose?.();
  state.assemblyPreviewGeometry = null;
  state.assemblyPreviewPromise = null;
  state.assemblyBounds = null;
  state.parts = supported.map((file, index) => buildPartState(file, index));
  state.solids = [];
  state.selectedPartId = state.parts[0]?.id || "";
  state.currentAssemblyLink = "base_link";
  renderAssembly();
}

async function inspectSingleStep(file) {
  const totalBytes = file.size;
  const baseLabel = `${file.name} / ${formatBytes(totalBytes)}`;
  const startedAt = Date.now();
  const statusTimer = window.setInterval(() => {
    const seconds = Math.max(1, Math.floor((Date.now() - startedAt) / 1000));
    el.stepStatus.textContent = `识别中 ${seconds}s`;
    el.stepFileName.textContent = `${baseLabel} / 正在识别 solids... ${seconds}s`;
  }, 1000);
  const controller = new AbortController();
  state.stepInspectAbort = controller;
  el.stepFileName.textContent = `${baseLabel} / 正在识别 solids...`;
  if (!el.stepRobotName.value.trim()) {
    el.stepRobotName.value = file.name.replace(/\.(stp|step)$/i, "").replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "");
  }
  const payload = new FormData();
  payload.append("file", file);
  payload.append("robot_name", el.stepRobotName.value.trim());
  payload.append("material", el.stepMaterial.value);
  payload.append("cad_unit", el.stepUnit.value);
  try {
    const result = await robots.inspectStepAssembly(payload, { signal: controller.signal });
    state.currentAssemblyId = result.assembly_id || "";
    state.assemblyPreviewUrl = result.preview_mesh_url || "";
    const unitScale = cadUnitScale(result.cad_unit || el.stepUnit.value);
    state.assemblyPreviewScale = unitScale;
    state.assemblyPreviewGeometry?.dispose?.();
    state.assemblyPreviewGeometry = null;
    state.assemblyPreviewPromise = null;
    state.assemblyBounds = combineBoundingBoxes(result.solids || []);
    state.solids = (result.solids || []).map((solid, index) => ({
      id: solid.id || `solid_${index + 1}`,
      file: null,
      path: solid.path,
      name: solid.name || solid.mesh_name || `solid_${index + 1}`,
      ext: ".stl",
      size: 0,
      link: "",
      xyz: [0, 0, 0],
      rpy: [0, 0, 0],
      visual: true,
      collision: true,
      previewStatus: "pending",
      previewMessage: `solid ${index + 1}`,
      previewGeometry: null,
      previewPromise: null,
      meshUrl: solid.meshUrl || solid.mesh_url || "",
      meshName: solid.meshName || solid.mesh_name || "",
      previewScale: unitScale,
      volume_m3: solid.volume_m3 || 0,
      mass_kg: solid.mass_kg || 0,
      bbox: solid.bbox || [],
      center: solid.center || [0, 0, 0],
    }));
    state.parts = state.solids.map((solid, index) => ({
      id: solid.id,
      file: null,
      path: solid.path,
      name: solid.name,
      ext: ".stl",
      size: 0,
      link: "",
      xyz: Array.isArray(solid.center) && solid.center.length >= 3
        ? solid.center.slice(0, 3).map((v) => Number((Number(v || 0) * unitScale).toFixed(6)))
        : [0, 0, 0],
      rpy: [0, 0, 0],
      visual: true,
      collision: true,
      previewStatus: "pending",
      previewMessage: "solid",
      previewGeometry: null,
      previewPromise: null,
      meshUrl: solid.meshUrl || solid.mesh_url || "",
      meshName: solid.meshName || solid.mesh_name || "",
      previewScale: unitScale,
      center: solid.center || [0, 0, 0],
    }));
    state.selectedPartId = state.parts[0]?.id || "";
    state.currentAssemblyLink = "base_link";
    renderAssembly();
    el.stepStatus.textContent = `solids ${result.solid_count || state.parts.length}`;
    el.stepFileName.textContent = `${baseLabel} / 已识别 ${result.solid_count || state.parts.length} 个 solids`;
    el.assemblyPreviewStatus.textContent = `已识别 ${result.solid_count || state.parts.length} 个 solids，预览按需加载`;
    el.assemblyPreviewStatus.dataset.status = "ok";
    if (result.warnings?.length) {
      el.stepError.textContent = result.warnings.join("；");
    }
  } catch (err) {
    if (err?.name === "AbortError") return;
    el.stepError.textContent = err instanceof ApiError ? err.message : "STEP solid 识别失败";
    el.stepStatus.textContent = "识别失败";
  } finally {
    window.clearInterval(statusTimer);
    if (state.stepInspectAbort === controller) state.stepInspectAbort = null;
  }
}

function collectPartAssignments() {
  return state.parts
    .filter((part) => part.link)
    .map((part) => ({
      solid_id: part.id,
      path: part.path,
      link: part.link,
      xyz: part.xyz,
      rpy: part.rpy,
      visual: part.visual,
      collision: part.collision,
    }));
}

async function onStepExport(e) {
  e.preventDefault();
  el.stepError.textContent = "";
  el.stepResult.innerHTML = "";
  const files = Array.from(el.stepFile.files || []);
  if (!files.length) {
    el.stepError.textContent = "请先选择 CAD 文件";
    return;
  }
  if (!el.stepRobotName.value.trim()) {
    el.stepError.textContent = "机器人名称不能为空";
    return;
  }

  const payload = new FormData();
  payload.append("robot_name", el.stepRobotName.value.trim());
  payload.append("vendor", el.stepVendor.value.trim());
  payload.append("template", el.stepTemplate.value);
  payload.append("material", el.stepMaterial.value);
  payload.append("cad_unit", el.stepUnit.value);
  payload.append("create_robot", el.stepCreateRobot.checked ? "true" : "false");
  payload.append("joints_json", JSON.stringify(collectStepJoints()));

  el.stepExportButton.disabled = true;
  el.stepStatus.textContent = "导出中";
  try {
    let result;
    if ((state.inputMode || "assembly") === "assembly") {
      if (!state.currentAssemblyId) {
        throw new Error("请先识别单 STEP 的 solids");
      }
      const assignments = collectPartAssignments();
      if (!assignments.length) {
        throw new Error("至少需要把一个 solid 分配到 URDF link");
      }
      payload.append("assembly_id", state.currentAssemblyId);
      payload.append("part_assignments_json", JSON.stringify(assignments));
      result = await robots.exportStepAssemblyUrdf(payload);
    } else {
      if (files.some((file) => !file.webkitRelativePath)) {
        throw new Error("文件夹模式需要选择整个目录");
      }
      const supported = files.filter((file) => CAD_MESH_EXTS.has(fileExt(file.name)));
      if (!supported.length) {
        throw new Error("文件夹里没有可导出的 CAD 文件");
      }
      const assignments = collectPartAssignments();
      if (!assignments.length) {
        throw new Error("至少需要把一个零件分配到 URDF link");
      }
      for (const file of files) {
        payload.append("files", file);
        payload.append("relative_paths", file.webkitRelativePath || file.name);
      }
      payload.append("part_assignments_json", JSON.stringify(assignments));
      result = await robots.exportStepFolderUrdf(payload);
    }
    renderStepResult(result);
    el.stepStatus.textContent = "已生成 URDF package";
    if (result.robot_id) await loadList();
  } catch (err) {
    el.stepError.textContent = err instanceof ApiError ? err.message : (err?.message || "导出失败");
    el.stepStatus.textContent = "导出失败";
  } finally {
    el.stepExportButton.disabled = false;
  }
}

async function fetchPartPreviewGeometry(part) {
  part.previewStatus = "loading";
  part.previewMessage = "loading mesh";
  renderPartList();

  const key = previewCacheKey(part);
  if (state.meshCache.has(key)) return state.meshCache.get(key).clone();

  let ext = part.ext;
  let buffer;
  const meshUrl = resolvePartMeshUrl(part);
  if (meshUrl) {
    const res = await fetch(meshUrl, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(formatPreviewError(res.status, text));
    }
    buffer = await res.arrayBuffer();
    ext = ".stl";
  } else if (ext === ".stp" || ext === ".step") {
    if (!part.file) {
      throw new Error("预览源缺失，请重新识别 STEP solids");
    }
    const payload = new FormData();
    payload.append("file", part.file);
    const res = await fetch("/api/robots/urdf/preview-mesh", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      body: payload,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(formatPreviewError(res.status, text));
    }
    buffer = await res.arrayBuffer();
    ext = ".stl";
  } else {
    if (!part.file || typeof part.file.arrayBuffer !== "function") {
      throw new Error("预览源缺失，请重新识别 CAD 文件");
    }
    buffer = await part.file.arrayBuffer();
  }

  let geometry;
  if (ext === ".stl") geometry = parseStlGeometry(buffer);
  else if (ext === ".obj") geometry = parseObjGeometry(new TextDecoder().decode(buffer));
  else throw new Error(`${ext || "mesh"} preview is not available yet`);

  normalizePreviewGeometryKeepPose(geometry, part.previewScale || 1);
  state.meshCache.set(key, geometry.clone());
  return geometry;
}
