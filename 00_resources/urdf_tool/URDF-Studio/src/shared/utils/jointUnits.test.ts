import test from 'node:test';
import assert from 'node:assert/strict';

import { hasEffectivelyFiniteJointLimits } from './jointUnits.ts';

test('hasEffectivelyFiniteJointLimits accepts ordinary authored bounds', () => {
  assert.equal(
    hasEffectivelyFiniteJointLimits({ lower: -Math.PI / 2, upper: Math.PI / 2 }),
    true,
  );
});

test('hasEffectivelyFiniteJointLimits keeps the 10000 boundary finite', () => {
  assert.equal(
    hasEffectivelyFiniteJointLimits({ lower: -10000, upper: 10000 }),
    true,
  );
});

test('hasEffectivelyFiniteJointLimits rejects IEEE max sentinel bounds used as pseudo-infinity', () => {
  assert.equal(
    hasEffectivelyFiniteJointLimits({ lower: -1.79769e308, upper: 1.79769e308 }),
    false,
  );
});

test('hasEffectivelyFiniteJointLimits rejects bounds larger than 10000 as effectively unbounded', () => {
  assert.equal(
    hasEffectivelyFiniteJointLimits({ lower: -10001, upper: 10001 }),
    false,
  );
});

test('hasEffectivelyFiniteJointLimits rejects missing or non-finite bounds', () => {
  assert.equal(hasEffectivelyFiniteJointLimits({ lower: Number.NEGATIVE_INFINITY, upper: 1 }), false);
  assert.equal(hasEffectivelyFiniteJointLimits({ lower: -1, upper: Number.POSITIVE_INFINITY }), false);
  assert.equal(hasEffectivelyFiniteJointLimits(undefined), false);
});
