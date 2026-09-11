import * as THREE from 'three';

const EPSILON = 1e-4;
const POLAR_EPSILON = 1e-6;
const THREE_ORBIT_CONTROLS_UP = new THREE.Vector3(0, 1, 0);
const WORKSPACE_Z_UP = new THREE.Vector3(0, 0, 1);

export interface UsdWorkerOrbitState {
  target: THREE.Vector3;
  radius: number;
  azimuth: number;
  polar: number;
  cameraUp: THREE.Vector3;
}

function resolveCameraUp(cameraUp: THREE.Vector3 | null | undefined): THREE.Vector3 {
  if (
    cameraUp &&
    Number.isFinite(cameraUp.x) &&
    Number.isFinite(cameraUp.y) &&
    Number.isFinite(cameraUp.z) &&
    cameraUp.lengthSq() > EPSILON * EPSILON
  ) {
    return cameraUp.clone().normalize();
  }

  return WORKSPACE_Z_UP.clone();
}

export function createUsdWorkerOrbitState(
  cameraPosition: THREE.Vector3,
  target = new THREE.Vector3(0, 0, 0),
  cameraUp?: THREE.Vector3 | null,
): UsdWorkerOrbitState {
  const resolvedCameraUp = resolveCameraUp(cameraUp);
  const offset = cameraPosition.clone().sub(target);
  const orbitControlsFrame = new THREE.Quaternion().setFromUnitVectors(
    resolvedCameraUp,
    THREE_ORBIT_CONTROLS_UP,
  );
  const spherical = new THREE.Spherical();

  offset.applyQuaternion(orbitControlsFrame);
  spherical.setFromVector3(offset);

  return {
    target: target.clone(),
    radius: Math.max(EPSILON, spherical.radius),
    azimuth: spherical.theta,
    polar: spherical.phi,
    cameraUp: resolvedCameraUp,
  };
}

export function applyUsdWorkerOrbitPointerDelta(
  orbit: UsdWorkerOrbitState,
  deltaX: number,
  deltaY: number,
  options: {
    rotationSpeed?: number;
  } = {},
): UsdWorkerOrbitState {
  const rotationSpeed = Number.isFinite(options.rotationSpeed)
    ? Number(options.rotationSpeed)
    : 0.005;

  orbit.azimuth -= deltaX * rotationSpeed;
  orbit.polar = Math.max(
    POLAR_EPSILON,
    Math.min(Math.PI - POLAR_EPSILON, orbit.polar - deltaY * rotationSpeed),
  );
  return orbit;
}

export function applyUsdWorkerOrbitZoomDelta(
  orbit: UsdWorkerOrbitState,
  deltaY: number,
  options: {
    zoomSpeed?: number;
    minRadius?: number;
    maxRadius?: number;
  } = {},
): UsdWorkerOrbitState {
  const zoomSpeed = Number.isFinite(options.zoomSpeed)
    ? Number(options.zoomSpeed)
    : 0.0015;
  const minRadius = Number.isFinite(options.minRadius)
    ? Number(options.minRadius)
    : 0.2;
  const maxRadius = Number.isFinite(options.maxRadius)
    ? Number(options.maxRadius)
    : 2000;

  orbit.radius = Math.max(minRadius, Math.min(maxRadius, orbit.radius * Math.exp(deltaY * zoomSpeed)));
  return orbit;
}

export function applyUsdWorkerOrbitPanDelta(
  orbit: UsdWorkerOrbitState,
  camera: THREE.PerspectiveCamera | THREE.Camera,
  deltaX: number,
  deltaY: number,
  options: {
    viewportHeight?: number;
    panSpeed?: number;
  } = {},
): UsdWorkerOrbitState {
  const viewportHeight = Number.isFinite(options.viewportHeight) && Number(options.viewportHeight) > 0
    ? Number(options.viewportHeight)
    : 1;
  const panSpeed = Number.isFinite(options.panSpeed)
    ? Number(options.panSpeed)
    : 0.9;
  const offset = camera.position.clone().sub(orbit.target);
  const perspectiveCamera = camera as THREE.PerspectiveCamera;
  const targetDistance = perspectiveCamera.isPerspectiveCamera
    ? offset.length() * Math.tan(THREE.MathUtils.degToRad(perspectiveCamera.fov / 2))
    : offset.length();
  const panOffset = new THREE.Vector3();
  const column = new THREE.Vector3();

  camera.updateMatrixWorld(true);
  column.setFromMatrixColumn(camera.matrix, 0);
  column.multiplyScalar((-2 * deltaX * targetDistance * panSpeed) / viewportHeight);
  panOffset.add(column);

  column.setFromMatrixColumn(camera.matrix, 1);
  column.multiplyScalar((2 * deltaY * targetDistance * panSpeed) / viewportHeight);
  panOffset.add(column);

  orbit.target.add(panOffset);
  return orbit;
}

export function applyUsdWorkerOrbitToCamera(
  orbit: UsdWorkerOrbitState,
  camera: THREE.PerspectiveCamera | THREE.Camera,
  controls?: { target: THREE.Vector3; update?: () => unknown } | null,
): void {
  const offset = new THREE.Vector3().setFromSphericalCoords(
    orbit.radius,
    orbit.polar,
    orbit.azimuth,
  );
  const cameraFrame = new THREE.Quaternion()
    .setFromUnitVectors(resolveCameraUp(orbit.cameraUp), THREE_ORBIT_CONTROLS_UP)
    .invert();

  offset.applyQuaternion(cameraFrame);
  controls?.target.copy(orbit.target);
  camera.position.copy(orbit.target).add(offset);
  camera.lookAt(orbit.target);
  camera.updateMatrixWorld(true);
  controls?.update?.();
}
