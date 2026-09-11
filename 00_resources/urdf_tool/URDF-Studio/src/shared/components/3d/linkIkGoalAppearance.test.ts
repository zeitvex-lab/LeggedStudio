import test from 'node:test';
import assert from 'node:assert/strict';

import {
  LINK_IK_GOAL_NAME,
  LINK_IK_GOAL_RENDER_ORDER,
  resolveLinkIkGoalPalette,
  resolveLinkIkGoalScales,
} from './linkIkGoalAppearance.ts';

function assertClose(actual: number, expected: number): void {
  assert.ok(Math.abs(actual - expected) < 1e-12, `expected ${actual} to be close to ${expected}`);
}

test('resolveLinkIkGoalPalette keeps light mode on system blue and dark mode brighter', () => {
  const lightPalette = resolveLinkIkGoalPalette('light');
  const darkPalette = resolveLinkIkGoalPalette('dark');

  assert.equal(LINK_IK_GOAL_NAME, '__ik_goal__');
  assert.equal(LINK_IK_GOAL_RENDER_ORDER, 9_990);
  assert.equal(lightPalette.shell, '#007AFF');
  assert.equal(lightPalette.ring, '#007AFF');
  assert.equal(darkPalette.shell, '#0ea5e9');
  assert.ok(darkPalette.haloOpacity > lightPalette.haloOpacity);
});

test('resolveLinkIkGoalScales stays proportional to the base handle radius', () => {
  const scales = resolveLinkIkGoalScales(0.03);

  assertClose(scales.haloRadius, 0.045);
  assertClose(scales.shellRadius, 0.0336);
  assertClose(scales.coreRadius, 0.0228);
  assertClose(scales.ringRadius, 0.0546);
  assertClose(scales.ringTubeRadius, 0.0036);
});
