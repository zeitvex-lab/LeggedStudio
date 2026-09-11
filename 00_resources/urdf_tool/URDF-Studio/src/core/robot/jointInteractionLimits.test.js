import test from 'node:test';
import assert from 'node:assert/strict';

import {
  clampJointInteractionValue,
  normalizeJointInteractionLimits,
} from './jointInteractionLimits.js';

test('normalizeJointInteractionLimits preserves authored one-sided limits when both bounds are present', () => {
  assert.deepEqual(
    normalizeJointInteractionLimits(10, 20, {
      lower: -180,
      upper: 180,
    }),
    {
      lower: 10,
      upper: 20,
    },
  );

  assert.deepEqual(
    normalizeJointInteractionLimits(-20, -10, {
      lower: -180,
      upper: 180,
    }),
    {
      lower: -20,
      upper: -10,
    },
  );
});

test('normalizeJointInteractionLimits falls back only for missing bounds', () => {
  assert.deepEqual(
    normalizeJointInteractionLimits(null, 20, {
      lower: -180,
      upper: 180,
    }),
    {
      lower: -180,
      upper: 20,
    },
  );

  assert.deepEqual(
    normalizeJointInteractionLimits(10, null, {
      lower: -180,
      upper: 180,
    }),
    {
      lower: 10,
      upper: 180,
    },
  );
});

test('normalizeJointInteractionLimits treats crossed bounds as an ordered range', () => {
  assert.deepEqual(normalizeJointInteractionLimits(2, 1), {
    lower: 1,
    upper: 2,
  });

  assert.equal(clampJointInteractionValue(1.25, 2, 1), 1.25);
});

test('clampJointInteractionValue keeps neutral zero only when the real range spans zero', () => {
  assert.equal(
    clampJointInteractionValue(0, 10, 20, {
      preserveNeutralZero: true,
    }),
    10,
  );
  assert.equal(
    clampJointInteractionValue(0, -20, -10, {
      preserveNeutralZero: true,
    }),
    -10,
  );
  assert.equal(
    clampJointInteractionValue(0, -20, 20, {
      preserveNeutralZero: true,
    }),
    0,
  );
});
