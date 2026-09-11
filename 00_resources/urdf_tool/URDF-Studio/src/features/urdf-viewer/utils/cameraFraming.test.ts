import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { computeCameraFrame } from './cameraFrame.ts';

test('frames the camera around the latest object position and updates the orbit target', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(2, 2, 2);

  const controls = {
    target: new THREE.Vector3(0, 0, 0),
    update: () => {},
  };

  const geometry = new THREE.BoxGeometry(2, 2, 2);
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.position.set(10, 0, 0);

  const root = new THREE.Group();
  root.add(mesh);

  const frame = computeCameraFrame(root, camera, controls.target);

  assert.ok(frame);
  controls.target.copy(frame.focusTarget);
  camera.position.copy(frame.cameraPosition);
  assert.ok(Math.abs(controls.target.x - 10) < 1e-6);
  assert.ok(Math.abs(controls.target.y) < 1e-6);
  assert.ok(Math.abs(controls.target.z) < 1e-6);
  assert.ok(camera.position.distanceTo(controls.target) > 0.1);
  assert.ok(camera.position.x > controls.target.x);

  geometry.dispose();
  (mesh.material as THREE.Material).dispose();
});
