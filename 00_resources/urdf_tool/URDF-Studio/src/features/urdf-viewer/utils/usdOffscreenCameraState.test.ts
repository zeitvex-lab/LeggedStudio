import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import {
  applyUsdOffscreenCameraState,
  areUsdOffscreenCameraStatesEqual,
  captureUsdOffscreenCameraState,
} from './usdOffscreenCameraState.ts';

test('captures and applies offscreen camera state with orbit target', () => {
  const sourceCamera = new THREE.PerspectiveCamera(42, 1.5, 0.2, 2500);
  sourceCamera.position.set(3, -4, 5);
  sourceCamera.up.set(0, 0, 1);
  sourceCamera.zoom = 1.25;
  sourceCamera.lookAt(0.5, -0.25, 0.75);
  sourceCamera.updateProjectionMatrix();
  sourceCamera.updateMatrixWorld(true);

  const state = captureUsdOffscreenCameraState(sourceCamera, new THREE.Vector3(0.5, -0.25, 0.75));

  const targetCamera = new THREE.PerspectiveCamera();
  let controlsUpdated = false;
  const controls = {
    target: new THREE.Vector3(),
    update: () => {
      controlsUpdated = true;
      return true;
    },
  };

  const changed = applyUsdOffscreenCameraState(targetCamera, controls, state);

  assert.equal(changed, true);
  assert.equal(controlsUpdated, true);
  assert.deepEqual(targetCamera.position.toArray(), [3, -4, 5]);
  assert.deepEqual(controls.target.toArray(), [0.5, -0.25, 0.75]);
  assert.equal(targetCamera.fov, 42);
  assert.equal(targetCamera.aspect, 1.5);
  assert.equal(targetCamera.near, 0.2);
  assert.equal(targetCamera.far, 2500);
  assert.equal(targetCamera.zoom, 1.25);
  assert.ok(
    areUsdOffscreenCameraStatesEqual(
      captureUsdOffscreenCameraState(targetCamera, controls.target),
      state,
    ),
  );
});

test('camera state comparison tolerates tiny numeric drift only', () => {
  const camera = new THREE.PerspectiveCamera(50, 2, 0.1, 1000);
  camera.position.set(1, 2, 3);
  camera.lookAt(0, 0, 0);
  const state = captureUsdOffscreenCameraState(camera, new THREE.Vector3(0, 0, 0));

  assert.equal(
    areUsdOffscreenCameraStatesEqual(state, {
      ...state,
      position: [state.position[0] + 1e-7, state.position[1], state.position[2]],
    }),
    true,
  );
  assert.equal(
    areUsdOffscreenCameraStatesEqual(state, {
      ...state,
      position: [state.position[0] + 1e-2, state.position[1], state.position[2]],
    }),
    false,
  );
});
