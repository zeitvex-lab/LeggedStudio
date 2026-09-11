import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveScreenSpaceUsdGeometryHit } from './usdScreenSpaceGeometryInteraction.ts';

function target(overrides = {}) {
  return {
    meta: { id: 'target' },
    layer: 'visual' as const,
    clientX: 100,
    clientY: 100,
    projectedWidth: 80,
    projectedHeight: 40,
    projectedArea: 3200,
    averageDepth: 0.5,
    ...overrides,
  };
}

test('resolveScreenSpaceUsdGeometryHit selects a projected visual target on exact raycast miss', () => {
  const resolved = resolveScreenSpaceUsdGeometryHit({
    pointerClientX: 100,
    pointerClientY: 100,
    projectedGeometry: [target({ meta: { id: 'thigh' } })],
  });

  assert.equal(resolved?.meta.id, 'thigh');
});

test('resolveScreenSpaceUsdGeometryHit rejects pointers outside the padded projected bounds', () => {
  const resolved = resolveScreenSpaceUsdGeometryHit({
    pointerClientX: 200,
    pointerClientY: 200,
    projectedGeometry: [target({ meta: { id: 'thigh' } })],
  });

  assert.equal(resolved, null);
});

test('resolveScreenSpaceUsdGeometryHit prefers the target nearest the projected center', () => {
  const resolved = resolveScreenSpaceUsdGeometryHit({
    pointerClientX: 124,
    pointerClientY: 100,
    projectedGeometry: [
      target({ meta: { id: 'large-base' }, clientX: 100, projectedWidth: 300, projectedArea: 90000 }),
      target({ meta: { id: 'leg' }, clientX: 124, projectedWidth: 60, projectedArea: 2400 }),
    ],
  });

  assert.equal(resolved?.meta.id, 'leg');
});

test('resolveScreenSpaceUsdGeometryHit respects explicit collision layer priority', () => {
  const resolved = resolveScreenSpaceUsdGeometryHit({
    pointerClientX: 100,
    pointerClientY: 100,
    interactionLayerPriority: ['collision', 'visual'],
    projectedGeometry: [
      target({ meta: { id: 'visual' }, layer: 'visual' }),
      target({ meta: { id: 'collision' }, layer: 'collision' }),
    ],
  });

  assert.equal(resolved?.meta.id, 'collision');
});
