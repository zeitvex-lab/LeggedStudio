import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import { createOriginMatrix } from './kinematics.ts';
import {
  buildJointAlignmentDeltaMatrix,
  computeBridgeOriginFromSnapFrames,
  computePointCoincidentOrigin,
  type JointAlignmentDelta,
} from './jointPickAlignment.ts';

function rigid(position: [number, number, number], euler: [number, number, number]): THREE.Matrix4 {
  return new THREE.Matrix4().compose(
    new THREE.Vector3(position[0], position[1], position[2]),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(euler[0], euler[1], euler[2], 'ZYX')),
    new THREE.Vector3(1, 1, 1),
  );
}

function assertMatrixNearlyEqual(actual: THREE.Matrix4, expected: THREE.Matrix4, message?: string) {
  for (let i = 0; i < 16; i += 1) {
    assert.ok(
      Math.abs(actual.elements[i] - expected.elements[i]) < 1e-6,
      message ?? `matrix element ${i}: ${actual.elements[i]} !== ${expected.elements[i]}`,
    );
  }
}

function snapRelativeToLink(linkWorld: THREE.Matrix4, snapWorld: THREE.Matrix4): THREE.Matrix4 {
  return linkWorld.clone().invert().multiply(snapWorld);
}

const PARENT_LINK = rigid([1, 2, 3], [0.1, 0.2, 0.3]);
const CHILD_LINK = rigid([5, -1, 2], [-0.2, 0.4, 0.1]);
const PARENT_SNAP = rigid([1.5, 2.2, 3.1], [0.5, 0, 0.2]);
const CHILD_SNAP = rigid([4.8, -1.1, 2.3], [0.1, -0.3, 0.6]);

test('computeBridgeOriginFromSnapFrames makes the child snap frame coincide with the parent snap frame', () => {
  const { matrix: origin } = computeBridgeOriginFromSnapFrames({
    parentSnapWorld: PARENT_SNAP,
    childSnapWorld: CHILD_SNAP,
    parentLinkWorld: PARENT_LINK,
    childLinkWorld: CHILD_LINK,
  });

  const childLinkWorldNew = PARENT_LINK.clone().multiply(origin);
  const snapRelLink = snapRelativeToLink(CHILD_LINK, CHILD_SNAP);
  const childSnapWorldNew = childLinkWorldNew.multiply(snapRelLink);

  assertMatrixNearlyEqual(childSnapWorldNew, PARENT_SNAP);
});

test('computeBridgeOriginFromSnapFrames applies the alignment delta in the snap frame', () => {
  const alignment: JointAlignmentDelta = {
    angleRad: 0.3,
    offset: { x: 0.1, y: -0.2, z: 0.05 },
    flip: true,
  };

  const { matrix: origin } = computeBridgeOriginFromSnapFrames({
    parentSnapWorld: PARENT_SNAP,
    childSnapWorld: CHILD_SNAP,
    parentLinkWorld: PARENT_LINK,
    childLinkWorld: CHILD_LINK,
    alignment,
  });

  const childLinkWorldNew = PARENT_LINK.clone().multiply(origin);
  const snapRelLink = snapRelativeToLink(CHILD_LINK, CHILD_SNAP);
  const childSnapWorldNew = childLinkWorldNew.multiply(snapRelLink);

  const expected = PARENT_SNAP.clone().multiply(buildJointAlignmentDeltaMatrix(alignment));
  assertMatrixNearlyEqual(childSnapWorldNew, expected);
});

test('computeBridgeOriginFromSnapFrames returns a transform that reconstructs its matrix (ZYX closed)', () => {
  const { matrix, transform } = computeBridgeOriginFromSnapFrames({
    parentSnapWorld: PARENT_SNAP,
    childSnapWorld: CHILD_SNAP,
    parentLinkWorld: PARENT_LINK,
    childLinkWorld: CHILD_LINK,
  });

  const reconstructed = createOriginMatrix({ xyz: transform.position, rpy: transform.rotation });
  assertMatrixNearlyEqual(reconstructed, matrix);
});

test('computePointCoincidentOrigin meets the points and preserves child orientation', () => {
  const parentPoint = new THREE.Vector3(1.5, 2.2, 3.1);
  const childPoint = new THREE.Vector3(4.8, -1.1, 2.3);

  const { matrix: origin } = computePointCoincidentOrigin({
    parentSnapPointWorld: parentPoint,
    childSnapPointWorld: childPoint,
    parentLinkWorld: PARENT_LINK,
    childLinkWorld: CHILD_LINK,
  });

  const childLinkWorldNew = PARENT_LINK.clone().multiply(origin);
  const childPointRelLink = childPoint.clone().applyMatrix4(CHILD_LINK.clone().invert());
  const childPointNew = childPointRelLink.applyMatrix4(childLinkWorldNew);

  assert.ok(childPointNew.distanceTo(parentPoint) < 1e-6, 'snap points should coincide');

  const orientationOld = new THREE.Quaternion().setFromRotationMatrix(CHILD_LINK);
  const orientationNew = new THREE.Quaternion().setFromRotationMatrix(childLinkWorldNew);
  assert.ok(orientationOld.angleTo(orientationNew) < 1e-6, 'child orientation should be preserved');
});

test('buildJointAlignmentDeltaMatrix is identity for the zero alignment', () => {
  const identity = buildJointAlignmentDeltaMatrix({
    angleRad: 0,
    offset: { x: 0, y: 0, z: 0 },
    flip: false,
  });
  assertMatrixNearlyEqual(identity, new THREE.Matrix4());
});
