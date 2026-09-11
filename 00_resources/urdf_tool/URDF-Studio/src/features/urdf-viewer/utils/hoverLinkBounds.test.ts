import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  choosePreferredHoverMatch,
  findNearestExpandedBoundsHit,
  type HoverMatch,
  resolvePreferredHoverMatch,
} from './hoverLinkBounds.ts';

interface TestHoverMeta {
  linkKey: string;
  role: 'visual' | 'collision';
}

function createMesh(position: [number, number, number], scale: [number, number, number] = [1, 1, 1]) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({ color: 0xffffff }),
  );
  mesh.position.set(...position);
  mesh.scale.set(...scale);
  mesh.updateMatrixWorld(true);
  return mesh;
}

function createCamera() {
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 0, 0);
  camera.lookAt(0, 0, -1);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

function projectPointToScreen(point: THREE.Vector3, camera: THREE.Camera) {
  const projected = point.clone().project(camera);
  return {
    x: ((projected.x + 1) * 0.5) * 1000,
    y: ((1 - projected.y) * 0.5) * 1000,
  };
}

test('findNearestExpandedBoundsHit finds a small front link even when the ray only grazes its expanded bounds', () => {
  const frontSmallMesh = createMesh([0.045, 0, -2], [0.08, 0.08, 0.08]);
  const backLargeMesh = createMesh([0, 0, -4], [1.5, 1.5, 1.5]);

  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0, 0, -1),
  );

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [
      { mesh: frontSmallMesh, meta: { linkKey: 'front', role: 'visual' } },
      { mesh: backLargeMesh, meta: { linkKey: 'back', role: 'visual' } },
    ],
    (meta) => meta.linkKey,
  );

  assert.ok(hit);
  assert.equal(hit?.meta.linkKey, 'front');
  assert.ok((hit?.padding ?? 0) > 0);
});

test('findNearestExpandedBoundsHit skips bounds fallback for large on-screen links', () => {
  const largeMesh = createMesh([0.62, 0, -2], [1, 1, 1]);
  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0, 0, -1),
  );

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [{ mesh: largeMesh, meta: { linkKey: 'large', role: 'visual' } }],
    (meta) => meta.linkKey,
    {
      camera: createCamera(),
      viewportWidth: 1000,
      viewportHeight: 1000,
    },
  );

  assert.equal(hit, null);
});

test('findNearestExpandedBoundsHit keeps bounds fallback for genuinely small on-screen links', () => {
  const tinyMesh = createMesh([0.045, 0, -2], [0.08, 0.08, 0.08]);
  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0, 0, -1),
  );

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [{ mesh: tinyMesh, meta: { linkKey: 'tiny', role: 'visual' } }],
    (meta) => meta.linkKey,
    {
      camera: createCamera(),
      viewportWidth: 1000,
      viewportHeight: 1000,
      pointerScreenX: 500,
      pointerScreenY: 500,
    },
  );

  assert.ok(hit);
  assert.equal(hit?.meta.linkKey, 'tiny');
});

test('findNearestExpandedBoundsHit rejects fallback when the pointer is visibly outside the projected mesh footprint', () => {
  const tinyNearMesh = createMesh([0.02, 0, -0.6], [0.02, 0.02, 0.02]);
  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0, 0, -1),
  );

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [{ mesh: tinyNearMesh, meta: { linkKey: 'tiny_near', role: 'visual' } }],
    (meta) => meta.linkKey,
    {
      camera: createCamera(),
      viewportWidth: 1000,
      viewportHeight: 1000,
      pointerScreenX: 500,
      pointerScreenY: 500,
    },
  );

  assert.equal(hit, null);
});

test('findNearestExpandedBoundsHit does not treat the empty gap between split meshes on the same link as hoverable space', () => {
  const leftMesh = createMesh([-0.04, 0, -3], [0.03, 0.03, 0.03]);
  const rightMesh = createMesh([0.04, 0, -3], [0.03, 0.03, 0.03]);
  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0, 0, -1),
  );

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [
      { mesh: leftMesh, meta: { linkKey: 'split_link', role: 'visual' } },
      { mesh: rightMesh, meta: { linkKey: 'split_link', role: 'visual' } },
    ],
    (meta) => meta.linkKey,
    {
      camera: createCamera(),
      viewportWidth: 1000,
      viewportHeight: 1000,
    },
  );

  assert.equal(hit, null);
});

test('findNearestExpandedBoundsHit does not let projected padding engulf a nearby small mesh', () => {
  const camera = createCamera();
  const nearMesh = createMesh([0.03, 0.03, -0.7], [0.02, 0.02, 0.02]);
  const pointerTarget = new THREE.Vector3(0.018, 0.019, -0.7);
  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    pointerTarget.clone().normalize(),
  );
  const screenPoint = projectPointToScreen(pointerTarget, camera);

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [{ mesh: nearMesh, meta: { linkKey: 'near_tiny', role: 'visual' } }],
    (meta) => meta.linkKey,
    {
      camera,
      viewportWidth: 1000,
      viewportHeight: 1000,
      pointerScreenX: screenPoint.x,
      pointerScreenY: screenPoint.y,
    },
  );

  assert.equal(hit, null);
});

test('findNearestExpandedBoundsHit respects mesh orientation instead of hovering empty rotated bounds corners', () => {
  const camera = createCamera();
  const rotatedMesh = createMesh([0.03, 0.03, -1.5], [0.015, 0.06, 0.015]);
  rotatedMesh.rotation.z = Math.PI / 4;
  rotatedMesh.updateMatrixWorld(true);

  const pointerTarget = new THREE.Vector3(-0.0005, 0.0025, -1.5);
  const ray = new THREE.Ray(
    new THREE.Vector3(0, 0, 0),
    pointerTarget.clone().normalize(),
  );
  const screenPoint = projectPointToScreen(pointerTarget, camera);

  const hit = findNearestExpandedBoundsHit<TestHoverMeta>(
    ray,
    [{ mesh: rotatedMesh, meta: { linkKey: 'rotated_link', role: 'visual' } }],
    (meta) => meta.linkKey,
    {
      camera,
      viewportWidth: 1000,
      viewportHeight: 1000,
      pointerScreenX: screenPoint.x,
      pointerScreenY: screenPoint.y,
    },
  );

  assert.equal(hit, null);
});

test('choosePreferredHoverMatch prefers the exact hit when both candidates resolve to the same link', () => {
  const exact: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'arm_link', role: 'visual' },
    distance: 1.8,
  };
  const bounds: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'arm_link', role: 'visual' },
    distance: 1.7,
    padding: 0.15,
  };

  const resolved = choosePreferredHoverMatch(exact, bounds, (meta) => meta.linkKey);
  assert.equal(resolved, exact);
});

test('choosePreferredHoverMatch keeps the exact hit when bounds belongs to a different link', () => {
  const exact: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'rear_link', role: 'visual' },
    distance: 2.8,
  };
  const bounds: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'front_link', role: 'visual' },
    distance: 2.45,
    padding: 0.1,
  };

  const resolved = choosePreferredHoverMatch(exact, bounds, (meta) => meta.linkKey);
  assert.equal(resolved, exact);
});

test('choosePreferredHoverMatch keeps the exact hit when bounds is only closer because of padding inflation', () => {
  const exact: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'target_link', role: 'visual' },
    distance: 2.52,
  };
  const bounds: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'neighbor_link', role: 'visual' },
    distance: 2.45,
    padding: 0.1,
  };

  const resolved = choosePreferredHoverMatch(exact, bounds, (meta) => meta.linkKey);
  assert.equal(resolved, exact);
});

test('resolvePreferredHoverMatch reports exact hits as the winning source', () => {
  const camera = createCamera();
  const tinyMesh = createMesh([0.045, 0, -2], [0.08, 0.08, 0.08]);
  const exact: HoverMatch<TestHoverMeta> = {
    meta: { linkKey: 'exact_link', role: 'visual' },
    distance: 1.5,
  };

  const resolved = resolvePreferredHoverMatch({
    exactMatch: exact,
    ray: new THREE.Ray(
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, -1),
    ),
    candidates: [{ mesh: tinyMesh, meta: { linkKey: 'bounds_link', role: 'visual' } }],
    getLinkKey: (meta) => meta.linkKey,
    boundsOptions: {
      camera,
      viewportWidth: 1000,
      viewportHeight: 1000,
      pointerScreenX: 500,
      pointerScreenY: 500,
    },
  });

  assert.ok(resolved);
  assert.equal(resolved?.match, exact);
  assert.equal(resolved?.source, 'exact');
});

test('resolvePreferredHoverMatch reports bounds hits when there is no exact mesh hit', () => {
  const tinyMesh = createMesh([0.045, 0, -2], [0.08, 0.08, 0.08]);

  const resolved = resolvePreferredHoverMatch({
    exactMatch: null,
    ray: new THREE.Ray(
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, -1),
    ),
    candidates: [{ mesh: tinyMesh, meta: { linkKey: 'bounds_link', role: 'visual' } }],
    getLinkKey: (meta) => meta.linkKey,
    boundsOptions: {
      camera: createCamera(),
      viewportWidth: 1000,
      viewportHeight: 1000,
      pointerScreenX: 500,
      pointerScreenY: 500,
    },
  });

  assert.ok(resolved);
  assert.equal(resolved?.match.meta.linkKey, 'bounds_link');
  assert.equal(resolved?.source, 'bounds');
});
