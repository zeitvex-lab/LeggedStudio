import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {
  DEFAULT_GROUND_PLANE_SIZE,
  resolveGroundPlaneLayout,
} from './groundPlaneSizing.ts';

test('resolveGroundPlaneLayout falls back to the compact default layout', () => {
  const layout = resolveGroundPlaneLayout(null);

  assert.equal(layout.centerX, 0);
  assert.equal(layout.centerY, 0);
  assert.equal(layout.size, DEFAULT_GROUND_PLANE_SIZE);
  assert.equal(layout.fadeFrom, 1);
  assert.equal(layout.fadeDistance, DEFAULT_GROUND_PLANE_SIZE * 100);
});

test('resolveGroundPlaneLayout keeps the ground plane anchored to the world origin', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(-12, -6, -1),
    new THREE.Vector3(24, 14, 7),
  );

  const layout = resolveGroundPlaneLayout(bounds);

  assert.equal(layout.centerX, 0);
  assert.equal(layout.centerY, 0);
  assert.equal(layout.size, 72);
  assert.equal(layout.fadeDistance, 72 * 100);
});

test('resolveGroundPlaneLayout does not enlarge until the model exceeds the default boundary', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(2, -3, -1),
    new THREE.Vector3(6.5, 4, 2),
  );

  const layout = resolveGroundPlaneLayout(bounds);

  assert.equal(layout.centerX, 0);
  assert.equal(layout.centerY, 0);
  assert.equal(layout.size, DEFAULT_GROUND_PLANE_SIZE);
});

test('resolveGroundPlaneLayout recenters the ground plane when the model footprint is far from the world origin', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(26, 41, -1),
    new THREE.Vector3(34, 49, 2),
  );

  const layout = resolveGroundPlaneLayout(bounds);

  assert.equal(layout.centerX, 30);
  assert.equal(layout.centerY, 46);
  assert.equal(layout.size, 146);
});

test('resolveGroundPlaneLayout caps oversized scenes', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(-200, -200, 0),
    new THREE.Vector3(200, 180, 100),
  );

  const layout = resolveGroundPlaneLayout(bounds);

  assert.equal(layout.size, 240);
  assert.equal(layout.fadeDistance, 240 * 100);
});
