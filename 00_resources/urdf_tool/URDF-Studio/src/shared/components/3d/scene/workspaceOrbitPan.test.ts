import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  DEFAULT_WORKSPACE_ORBIT_PAN_TUNING,
  resolveWorkspaceOrbitPanSpeed,
  resolveWorkspaceOrbitZoomSpeed,
} from './workspaceOrbitPan.ts';

test('resolveWorkspaceOrbitPanSpeed keeps the base speed when zoom level is comfortable', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(2, 0, 0);

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    sceneBounds: new THREE.Box3(
      new THREE.Vector3(-0.5, -0.5, -0.5),
      new THREE.Vector3(0.5, 0.5, 0.5),
    ),
    minDistance: 0.1,
  });

  assert.equal(panSpeed, 0.9);
});

test('resolveWorkspaceOrbitPanSpeed boosts close-range panning for perspective inspection', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(0.12, 0, 0);

  const sceneBounds = new THREE.Box3(
    new THREE.Vector3(-0.5, -0.5, -0.5),
    new THREE.Vector3(0.5, 0.5, 0.5),
  );
  const sceneDiagonal = sceneBounds.getSize(new THREE.Vector3()).length();
  const distanceFloor =
    Math.sqrt(sceneDiagonal) * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.closeRangeDistanceFactor;

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    sceneBounds,
    minDistance: 0.02,
  });

  assert.ok(panSpeed > 0.9, 'expected close inspection to receive a pan speed boost');
  assert.equal(panSpeed, 0.9 * (distanceFloor / 0.12));
});

test('resolveWorkspaceOrbitPanSpeed caps the boost so ultra-close zooms do not overshoot', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(0.01, 0, 0);

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    sceneBounds: new THREE.Box3(
      new THREE.Vector3(-0.5, -0.5, -0.5),
      new THREE.Vector3(0.5, 0.5, 0.5),
    ),
    minDistance: 0.02,
  });

  assert.equal(panSpeed, 0.9 * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.maxBoost);
});

test('resolveWorkspaceOrbitPanSpeed keeps elongated scenes inside the close-range boost cap', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(0.1, 0, 0);

  const sceneBounds = new THREE.Box3(
    new THREE.Vector3(-0.05, -0.05, -0.05),
    new THREE.Vector3(0.05, 0.05, 50),
  );

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    sceneBounds,
    minDistance: 0.02,
  });

  assert.equal(panSpeed, 0.9 * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.maxBoost);
});

test('resolveWorkspaceOrbitPanSpeed damps far-target panning inside a large scene', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(25, 0, 0);

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    sceneBounds: new THREE.Box3(
      new THREE.Vector3(-50, -0.5, -0.5),
      new THREE.Vector3(50, 0.5, 0.5),
    ),
    minDistance: 0.02,
  });

  assert.ok(panSpeed < 0.9, 'expected distant pivots in large scenes to pan slower');
  assert.ok(
    panSpeed >= 0.9 * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.minFarPanScale,
    'expected far-distance damping to stay usable',
  );
});

test('resolveWorkspaceOrbitPanSpeed keeps far-distance damping above the minimum scale', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(10_000, 0, 0);

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    sceneBounds: new THREE.Box3(
      new THREE.Vector3(-50, -0.5, -0.5),
      new THREE.Vector3(50, 0.5, 0.5),
    ),
    minDistance: 0.02,
  });

  assert.ok(panSpeed >= 0.9 * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.minFarPanScale);
});

test('resolveWorkspaceOrbitPanSpeed falls back to minDistance when scene bounds are unavailable', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(0.05, 0, 0);

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    minDistance: 0.1,
  });

  assert.equal(panSpeed, 0.9 * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.maxBoost);
});

test('resolveWorkspaceOrbitPanSpeed leaves orthographic cameras unchanged', () => {
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 1000);
  camera.position.set(0.02, 0, 0);

  const panSpeed = resolveWorkspaceOrbitPanSpeed({
    basePanSpeed: 0.9,
    camera,
    target: new THREE.Vector3(0, 0, 0),
    minDistance: 0.1,
  });

  assert.equal(panSpeed, 0.9);
});

test('resolveWorkspaceOrbitZoomSpeed damps large-scene zoom without boosting close views', () => {
  const target = new THREE.Vector3(0, 0, 0);
  const sceneBounds = new THREE.Box3(
    new THREE.Vector3(-50, -0.5, -0.5),
    new THREE.Vector3(50, 0.5, 0.5),
  );

  const farCamera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  farCamera.position.set(25, 0, 0);

  const farZoomSpeed = resolveWorkspaceOrbitZoomSpeed({
    baseZoomSpeed: 1.15,
    camera: farCamera,
    target,
    sceneBounds,
    minDistance: 0.02,
  });

  assert.ok(farZoomSpeed < 1.15);
  assert.ok(farZoomSpeed >= 1.15 * DEFAULT_WORKSPACE_ORBIT_PAN_TUNING.minZoomScale);

  const closeCamera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  closeCamera.position.set(0.1, 0, 0);

  const closeZoomSpeed = resolveWorkspaceOrbitZoomSpeed({
    baseZoomSpeed: 1.15,
    camera: closeCamera,
    target,
    sceneBounds: new THREE.Box3(
      new THREE.Vector3(-0.5, -0.5, -0.5),
      new THREE.Vector3(0.5, 0.5, 0.5),
    ),
    minDistance: 0.02,
  });

  assert.equal(closeZoomSpeed, 1.15);
});
