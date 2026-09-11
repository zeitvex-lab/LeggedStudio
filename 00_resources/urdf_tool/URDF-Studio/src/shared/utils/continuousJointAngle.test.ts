import assert from 'node:assert/strict';
import test from 'node:test';

import { unwrapContinuousJointAngle, wrapContinuousJointAngle } from './continuousJointAngle.ts';

test('wrapContinuousJointAngle keeps equivalent angles inside the principal interval', () => {
  assert.equal(wrapContinuousJointAngle(0), 0);
  assert.ok(Math.abs(wrapContinuousJointAngle(Math.PI * 2 + Math.PI / 3) - Math.PI / 3) < 1e-12);
  assert.ok(Math.abs(wrapContinuousJointAngle(-Math.PI * 2 - Math.PI / 4) + Math.PI / 4) < 1e-12);
});

test('unwrapContinuousJointAngle keeps runtime feedback near the accumulated reference', () => {
  const referenceAngle = Math.PI * 2 + Math.PI / 6;
  const runtimeAngle = Math.PI / 6;

  assert.ok(
    Math.abs(unwrapContinuousJointAngle(runtimeAngle, referenceAngle) - referenceAngle) < 1e-12,
  );
});

test('unwrapContinuousJointAngle preserves negative accumulated turns', () => {
  const referenceAngle = -Math.PI * 4 - Math.PI / 5;
  const runtimeAngle = -Math.PI / 5;

  assert.ok(
    Math.abs(unwrapContinuousJointAngle(runtimeAngle, referenceAngle) - referenceAngle) < 1e-12,
  );
});
