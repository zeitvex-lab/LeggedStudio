import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  resolveScreenSpaceHelperInteraction,
  type ProjectedHelperInteractionTarget,
} from './screenSpaceHelperInteraction.ts';

function createProjectedHelperTarget(
  overrides: Partial<ProjectedHelperInteractionTarget> = {},
): ProjectedHelperInteractionTarget {
  return {
    type: 'joint',
    id: 'joint1',
    helperKind: 'joint-axis',
    layer: 'joint-axis',
    clientX: 200,
    clientY: 120,
    projectedWidth: 4,
    projectedHeight: 4,
    projectedArea: 16,
    averageDepth: 0.25,
    sourceName: '__joint_axis__',
    object: new THREE.Object3D(),
    ...overrides,
  };
}

test('resolveScreenSpaceHelperInteraction returns helper when pointer is inside the padded helper footprint', () => {
  const projectedHelpers = [createProjectedHelperTarget()];

  const result = resolveScreenSpaceHelperInteraction({
    pointerClientX: 208,
    pointerClientY: 120,
    projectedHelpers,
    interactionLayerPriority: ['joint-axis', 'collision', 'visual'],
  });

  assert.equal(result?.targetKind, 'helper');
  assert.equal(result?.type, 'joint');
  assert.equal(result?.id, 'joint1');
  assert.equal(result?.helperKind, 'joint-axis');
});

test('resolveScreenSpaceHelperInteraction prefers the closer helper when multiple visible helpers overlap', () => {
  const projectedHelpers = [
    createProjectedHelperTarget({ id: 'joint-far', clientX: 240, clientY: 120 }),
    createProjectedHelperTarget({ id: 'joint-near', clientX: 205, clientY: 120 }),
  ];

  const result = resolveScreenSpaceHelperInteraction({
    pointerClientX: 206,
    pointerClientY: 120,
    projectedHelpers,
    interactionLayerPriority: ['joint-axis', 'collision', 'visual'],
  });

  assert.equal(result?.id, 'joint-near');
});

test('resolveScreenSpaceHelperInteraction returns null when pointer is outside the helper footprint', () => {
  const projectedHelpers = [createProjectedHelperTarget()];

  const result = resolveScreenSpaceHelperInteraction({
    pointerClientX: 260,
    pointerClientY: 120,
    projectedHelpers,
    interactionLayerPriority: ['joint-axis', 'collision', 'visual'],
  });

  assert.equal(result, null);
});

test('resolveScreenSpaceHelperInteraction does not use padded fallback for inertia helpers', () => {
  const projectedHelpers = [
    createProjectedHelperTarget({
      type: 'link',
      id: 'base_link',
      helperKind: 'inertia',
      layer: 'inertia',
      sourceName: '__inertia_box__',
      projectedWidth: 8,
      projectedHeight: 8,
      projectedArea: 64,
    }),
  ];

  const result = resolveScreenSpaceHelperInteraction({
    pointerClientX: 208,
    pointerClientY: 120,
    projectedHelpers,
    interactionLayerPriority: ['inertia', 'collision', 'visual'],
  });

  assert.equal(result, null);
});

test('resolveScreenSpaceHelperInteraction does not use screen-space fallback for origin-axes', () => {
  const projectedHelpers = [
    createProjectedHelperTarget({
      type: 'link',
      id: 'base_link',
      helperKind: 'origin-axes',
      layer: 'origin-axes',
      sourceName: '__origin_axes__',
      projectedWidth: 10,
      projectedHeight: 10,
      projectedArea: 100,
    }),
  ];

  const result = resolveScreenSpaceHelperInteraction({
    pointerClientX: 204,
    pointerClientY: 120,
    projectedHelpers,
    interactionLayerPriority: ['origin-axes', 'collision', 'visual'],
  });

  assert.equal(result, null);
});

test('resolveScreenSpaceHelperInteraction keeps origin-axes outside the padded-helper path', () => {
  const projectedHelpers = [
    createProjectedHelperTarget({
      type: 'link',
      id: 'base_link',
      helperKind: 'origin-axes',
      layer: 'origin-axes',
      sourceName: '__origin_axes__',
      projectedWidth: 10,
      projectedHeight: 10,
      projectedArea: 100,
    }),
  ];

  const result = resolveScreenSpaceHelperInteraction({
    pointerClientX: 206,
    pointerClientY: 126,
    projectedHelpers,
    interactionLayerPriority: ['origin-axes', 'collision', 'visual'],
  });

  assert.equal(result, null);
});
