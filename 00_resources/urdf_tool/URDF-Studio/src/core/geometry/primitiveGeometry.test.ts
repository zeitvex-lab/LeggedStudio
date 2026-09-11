import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canonicalizeAxis,
  computeAxisAlignmentScore,
  computeCapsuleVolume,
  computeCylinderVolume,
} from './primitiveGeometry.ts';

test('canonicalizeAxis normalizes and gives opposite axes the same canonical direction', () => {
  assert.deepEqual(canonicalizeAxis({ x: -2, y: 0, z: 0 }), { x: 1, y: 0, z: 0 });
  assert.deepEqual(canonicalizeAxis({ x: 0, y: -3, z: 0 }), { x: 0, y: 1, z: 0 });
  assert.deepEqual(canonicalizeAxis({ x: 0, y: 0, z: -4 }), { x: 0, y: 0, z: 1 });
});

test('canonicalizeAxis rejects degenerate or invalid axes', () => {
  assert.equal(canonicalizeAxis({ x: 0, y: 0, z: 0 }), null);
  assert.equal(canonicalizeAxis({ x: Number.NaN, y: 1, z: 0 }), null);
});

test('computeAxisAlignmentScore compares normalized absolute axis alignment', () => {
  assert.equal(
    computeAxisAlignmentScore({ x: -2, y: 0, z: 0 }, { x: 5, y: 0, z: 0 }),
    1,
  );
  assert.equal(
    computeAxisAlignmentScore({ x: 0, y: 1, z: 0 }, { x: 0, y: 0, z: 1 }),
    0,
  );
  assert.equal(
    computeAxisAlignmentScore({ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 1 }),
    Number.NEGATIVE_INFINITY,
  );
});

test('computeCylinderVolume clamps invalid length to zero like existing primitive fitting', () => {
  assert.equal(computeCylinderVolume(2, 3), Math.PI * 4 * 3);
  assert.equal(computeCylinderVolume(2, -3), 0);
});

test('computeCapsuleVolume preserves the existing total-length formula and radius clamp', () => {
  const unclamped = Math.PI * 4 * 10 - (2 / 3) * Math.PI * 8;
  assert.equal(computeCapsuleVolume(10, 2), unclamped);

  const clampedRadius = 2;
  const clamped = Math.PI * clampedRadius * clampedRadius * 4 - (2 / 3) * Math.PI * 8;
  assert.equal(computeCapsuleVolume(4, 10), clamped);
  assert.equal(computeCapsuleVolume(0, 2), 0);
});
