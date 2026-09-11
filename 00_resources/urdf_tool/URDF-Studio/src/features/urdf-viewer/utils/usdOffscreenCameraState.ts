import * as THREE from 'three';

export type UsdOffscreenCameraTuple3 = [number, number, number];
export type UsdOffscreenCameraTuple4 = [number, number, number, number];

export interface UsdOffscreenCameraState {
  kind: 'perspective';
  position: UsdOffscreenCameraTuple3;
  quaternion: UsdOffscreenCameraTuple4;
  up: UsdOffscreenCameraTuple3;
  target: UsdOffscreenCameraTuple3;
  fov: number;
  near: number;
  far: number;
  zoom: number;
  aspect: number;
}

export interface UsdOffscreenOrbitControlsLike {
  target: THREE.Vector3;
  update?: () => unknown;
}

const CAMERA_STATE_EPSILON = 1e-5;

function vectorToTuple(vector: THREE.Vector3): UsdOffscreenCameraTuple3 {
  return [vector.x, vector.y, vector.z];
}

function quaternionToTuple(quaternion: THREE.Quaternion): UsdOffscreenCameraTuple4 {
  return [quaternion.x, quaternion.y, quaternion.z, quaternion.w];
}

function setVectorFromTuple(vector: THREE.Vector3, tuple: UsdOffscreenCameraTuple3): void {
  vector.set(tuple[0], tuple[1], tuple[2]);
}

function setQuaternionFromTuple(
  quaternion: THREE.Quaternion,
  tuple: UsdOffscreenCameraTuple4,
): void {
  quaternion.set(tuple[0], tuple[1], tuple[2], tuple[3]).normalize();
}

function finiteOrFallback(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

function numberClose(left: number, right: number, epsilon = CAMERA_STATE_EPSILON): boolean {
  return Math.abs(left - right) <= epsilon;
}

function tupleClose(
  left: readonly number[],
  right: readonly number[],
  epsilon = CAMERA_STATE_EPSILON,
): boolean {
  return left.length === right.length && left.every((value, index) => numberClose(value, right[index], epsilon));
}

export function captureUsdOffscreenCameraState(
  camera: THREE.PerspectiveCamera,
  target: THREE.Vector3,
): UsdOffscreenCameraState {
  camera.updateMatrixWorld(true);

  return {
    kind: 'perspective',
    position: vectorToTuple(camera.position),
    quaternion: quaternionToTuple(camera.quaternion),
    up: vectorToTuple(camera.up),
    target: vectorToTuple(target),
    fov: camera.fov,
    near: camera.near,
    far: camera.far,
    zoom: camera.zoom,
    aspect: camera.aspect,
  };
}

export function areUsdOffscreenCameraStatesEqual(
  left: UsdOffscreenCameraState | null | undefined,
  right: UsdOffscreenCameraState | null | undefined,
  epsilon = CAMERA_STATE_EPSILON,
): boolean {
  if (!left || !right) {
    return left === right;
  }

  return (
    left.kind === right.kind &&
    tupleClose(left.position, right.position, epsilon) &&
    tupleClose(left.quaternion, right.quaternion, epsilon) &&
    tupleClose(left.up, right.up, epsilon) &&
    tupleClose(left.target, right.target, epsilon) &&
    numberClose(left.fov, right.fov, epsilon) &&
    numberClose(left.near, right.near, epsilon) &&
    numberClose(left.far, right.far, epsilon) &&
    numberClose(left.zoom, right.zoom, epsilon) &&
    numberClose(left.aspect, right.aspect, epsilon)
  );
}

export function applyUsdOffscreenCameraState(
  camera: THREE.PerspectiveCamera,
  controls: UsdOffscreenOrbitControlsLike | null | undefined,
  state: UsdOffscreenCameraState | null | undefined,
): boolean {
  if (!state) {
    return false;
  }

  const before = captureUsdOffscreenCameraState(
    camera,
    controls?.target ?? new THREE.Vector3(state.target[0], state.target[1], state.target[2]),
  );

  setVectorFromTuple(camera.position, state.position);
  setVectorFromTuple(camera.up, state.up);
  camera.fov = finiteOrFallback(state.fov, camera.fov);
  camera.near = finiteOrFallback(state.near, camera.near);
  camera.far = finiteOrFallback(state.far, camera.far);
  camera.zoom = finiteOrFallback(state.zoom, camera.zoom);
  camera.aspect = finiteOrFallback(state.aspect, camera.aspect);

  if (controls) {
    controls.target.set(state.target[0], state.target[1], state.target[2]);
    controls.update?.();
  }

  setQuaternionFromTuple(camera.quaternion, state.quaternion);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);

  return !areUsdOffscreenCameraStatesEqual(before, captureUsdOffscreenCameraState(
    camera,
    controls?.target ?? new THREE.Vector3(state.target[0], state.target[1], state.target[2]),
  ));
}
