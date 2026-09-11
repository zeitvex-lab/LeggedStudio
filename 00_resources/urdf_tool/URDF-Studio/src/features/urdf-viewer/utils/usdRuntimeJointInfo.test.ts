import test from 'node:test';
import assert from 'node:assert/strict';

import { JointType } from '@/types';
import {
  clampUsdRuntimeJointAngleDegrees,
  createUsdRuntimeJointInfo,
  resolveUsdRuntimeJointLimitsRadians,
} from './usdRuntimeJointInfo';

function assertClose(actual: number | undefined, expected: number) {
  assert.ok(actual !== undefined);
  assert.ok(Math.abs(actual - expected) < 1e-9);
}

test('createUsdRuntimeJointInfo preserves authored one-sided joint limits', () => {
  const jointInfo = createUsdRuntimeJointInfo(
    {
      type: JointType.REVOLUTE,
      limit: {
        lower: undefined,
        upper: Math.PI / 3,
      },
    },
    Math.PI / 6,
  );

  assertClose(jointInfo.angleDeg, 30);
  assert.equal(jointInfo.lowerLimitDeg, undefined);
  assertClose(jointInfo.upperLimitDeg, 60);
});

test('clampUsdRuntimeJointAngleDegrees only clamps when finite authored bounds exist', () => {
  assertClose(
    clampUsdRuntimeJointAngleDegrees(
      {
        type: JointType.REVOLUTE,
        limit: {
          lower: Math.PI / 6,
          upper: Math.PI / 3,
        },
      },
      10,
    ),
    30,
  );

  assert.equal(
    clampUsdRuntimeJointAngleDegrees(
      {
        type: JointType.REVOLUTE,
        limit: {
          lower: undefined,
          upper: Math.PI / 3,
        },
      },
      10,
    ),
    10,
  );

  assert.equal(
    clampUsdRuntimeJointAngleDegrees(
      {
        type: JointType.CONTINUOUS,
        limit: {
          lower: 0,
          upper: 0,
        },
      },
      540,
    ),
    540,
  );
});

test('resolveUsdRuntimeJointLimitsRadians falls back per bound', () => {
  assert.deepEqual(
    resolveUsdRuntimeJointLimitsRadians(
      {
        upperLimitDeg: 90,
      },
      {
        lower: -Math.PI / 4,
        upper: Math.PI / 4,
      },
    ),
    {
      lower: -Math.PI / 4,
      upper: Math.PI / 2,
    },
  );

  assert.deepEqual(
    resolveUsdRuntimeJointLimitsRadians(
      {
        upperLimitDeg: 90,
      },
      undefined,
    ),
    {
      lower: undefined,
      upper: Math.PI / 2,
    },
  );
});
