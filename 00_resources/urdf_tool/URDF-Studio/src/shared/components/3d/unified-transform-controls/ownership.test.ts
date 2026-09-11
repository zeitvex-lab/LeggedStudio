import assert from 'node:assert/strict';
import test from 'node:test';

import { resolvePreferredUniversalOwner } from './ownership.ts';
import type { VisibleControlHit } from './gizmoCore.ts';

const createHit = (
  owner: 'translate' | 'rotate',
  axis: 'X' | 'Y' | 'Z',
  score = 0.12,
): VisibleControlHit => ({
  owner,
  axis,
  renderOrder: 10006,
  distance: 1,
  score,
});

test('resolvePreferredUniversalOwner prioritizes a visible rotate hit over stale translate hover', () => {
  const owner = resolvePreferredUniversalOwner({
    translateHovered: true,
    rotateHovered: false,
    translateHit: null,
    rotateHit: createHit('rotate', 'Z'),
    previousOwner: 'translate',
  });

  assert.equal(owner, 'rotate');
});

test('resolvePreferredUniversalOwner falls back to hover ownership when no visible hit exists', () => {
  const owner = resolvePreferredUniversalOwner({
    translateHovered: false,
    rotateHovered: true,
    translateHit: null,
    rotateHit: null,
    previousOwner: null,
  });

  assert.equal(owner, 'rotate');
});

test('resolvePreferredUniversalOwner keeps the better visible translate hit when both controls report hits', () => {
  const owner = resolvePreferredUniversalOwner({
    translateHovered: false,
    rotateHovered: true,
    translateHit: createHit('translate', 'X', 0.05),
    rotateHit: createHit('rotate', 'Y', 0.25),
    previousOwner: null,
  });

  assert.equal(owner, 'translate');
});
