import test from 'node:test';
import assert from 'node:assert/strict';

import {
  resolveUsdStageInteractionPolicy,
  resolveUsdStageJointRotationRuntime,
} from './usdInteractionPolicy.ts';

test('uses direct mesh selection when mode is `editor` so USD matches URDF/MJCF picking behavior', () => {
  assert.deepEqual(resolveUsdStageInteractionPolicy('editor'), {
    enableContinuousHover: true,
    enableJointRotation: true,
    enableMeshSelection: true,
  });
});

test('detail keeps the merged edit interaction policy when tool mode is omitted', () => {
  assert.deepEqual(resolveUsdStageInteractionPolicy('editor'), {
    enableContinuousHover: true,
    enableJointRotation: true,
    enableMeshSelection: true,
  });
});

test('disables continuous hover in pure view mode so pointer browsing stays read-only', () => {
  assert.deepEqual(resolveUsdStageInteractionPolicy('editor', 'view'), {
    enableContinuousHover: false,
    enableJointRotation: false,
    enableMeshSelection: false,
  });
});

test('disables USD joint rotation in pure view mode so clicking stays read-only', () => {
  assert.deepEqual(resolveUsdStageJointRotationRuntime({
    mode: 'editor',
    showVisual: true,
    showCollision: false,
    toolMode: 'view',
  }), {
    enabled: false,
    pickSubType: null,
  });
});

test('enables USD joint rotation in merged edit mode when visual meshes are the active interaction target', () => {
  assert.deepEqual(resolveUsdStageJointRotationRuntime({
    mode: 'editor',
    showVisual: true,
    showCollision: true,
    showCollisionAlwaysOnTop: false,
    toolMode: 'select',
  }), {
    enabled: true,
    pickSubType: 'visual',
  });
});

test('disables USD joint rotation when collision meshes are the active interaction target', () => {
  assert.deepEqual(resolveUsdStageJointRotationRuntime({
    mode: 'editor',
    showVisual: true,
    showCollision: true,
    showCollisionAlwaysOnTop: true,
    toolMode: 'select',
  }), {
    enabled: false,
    pickSubType: 'collision',
  });
});

test('disables USD joint rotation when interactionLayerPriority promotes collision over visual', () => {
  assert.deepEqual(resolveUsdStageJointRotationRuntime({
    mode: 'editor',
    showVisual: true,
    showCollision: true,
    showCollisionAlwaysOnTop: false,
    interactionLayerPriority: ['collision', 'visual'],
    toolMode: 'select',
  }), {
    enabled: false,
    pickSubType: 'collision',
  });
});

test('disables USD joint rotation while the measure tool is active', () => {
  assert.deepEqual(resolveUsdStageJointRotationRuntime({
    mode: 'editor',
    showVisual: true,
    showCollision: false,
    toolMode: 'measure',
  }), {
    enabled: false,
    pickSubType: null,
  });
});
