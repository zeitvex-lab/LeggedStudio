import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import {
  FUSION_TRANSLATE_PLANE_OFFSET,
  FUSION_TRANSLATE_PLANE_SIZE,
  createFusionTranslatePlaneGeometry,
  createFusionTranslatePlaneOutlineGeometry,
  getFusionTranslateCenterDragPlane,
  getFusionTranslatePlaneCenter,
  getFusionTranslatePlaneDragPlane,
  getFusionTranslatePlaneNormalAxis,
  resolveFusionTranslatePlanarDelta,
} from './fusionTranslatePlane.ts';

const EPSILON = 1e-8;

const assertClose = (actual: number, expected: number, label: string) => {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${label}: ${actual} !== ${expected}`);
};

test('translate plane centers sit between their two axes', () => {
  const xy = getFusionTranslatePlaneCenter('XY');
  const yz = getFusionTranslatePlaneCenter('YZ');
  const xz = getFusionTranslatePlaneCenter('XZ');

  assert.deepEqual(xy.toArray(), [FUSION_TRANSLATE_PLANE_OFFSET, FUSION_TRANSLATE_PLANE_OFFSET, 0]);
  assert.deepEqual(yz.toArray(), [0, FUSION_TRANSLATE_PLANE_OFFSET, FUSION_TRANSLATE_PLANE_OFFSET]);
  assert.deepEqual(xz.toArray(), [FUSION_TRANSLATE_PLANE_OFFSET, 0, FUSION_TRANSLATE_PLANE_OFFSET]);
});

test('translate plane normals resolve to the missing axis', () => {
  assert.equal(getFusionTranslatePlaneNormalAxis('XY'), 'Z');
  assert.equal(getFusionTranslatePlaneNormalAxis('YZ'), 'X');
  assert.equal(getFusionTranslatePlaneNormalAxis('XZ'), 'Y');
});

test('translate plane geometries expose a fill and four outline segments', () => {
  const fill = createFusionTranslatePlaneGeometry({ plane: 'XY' });
  const outline = createFusionTranslatePlaneOutlineGeometry({ plane: 'XY' });

  assert.equal(fill.getAttribute('position').count, 6);
  assert.equal(outline.getAttribute('position').count, 8);
  assert.ok(fill.boundingSphere);
  assert.ok(outline.boundingSphere);
  assert.ok((fill.boundingSphere?.radius ?? 0) > FUSION_TRANSLATE_PLANE_SIZE * 0.5);

  fill.dispose();
  outline.dispose();
});

test('plane drag plane follows the rotated missing axis', () => {
  const quaternion = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(0, 1, 0),
    Math.PI / 2,
  );
  const plane = getFusionTranslatePlaneDragPlane({
    origin: new THREE.Vector3(),
    plane: 'XY',
    spaceQuaternion: quaternion,
  });

  assert.ok(plane.normal.distanceTo(new THREE.Vector3(1, 0, 0)) < EPSILON);
});

test('center drag plane uses the camera direction as its normal', () => {
  const direction = new THREE.Vector3(2, 0, 0).normalize();
  const plane = getFusionTranslateCenterDragPlane({
    cameraDirection: direction,
    origin: new THREE.Vector3(1, 2, 3),
  });

  assert.ok(plane.normal.distanceTo(direction) < EPSILON);
  assertClose(plane.distanceToPoint(new THREE.Vector3(1, 2, 3)), 0, 'origin on plane');
});

test('planar delta keeps only the selected plane components and applies snap', () => {
  const delta = resolveFusionTranslatePlanarDelta({
    axesWorld: [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0)],
    intersection: new THREE.Vector3(0.26, 0.11, 0.9),
    snap: 0.1,
    startIntersection: new THREE.Vector3(0, 0, 0.9),
  });

  assert.deepEqual(delta.toArray(), [0.30000000000000004, 0.1, 0]);
});
