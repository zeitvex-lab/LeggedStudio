import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveInteractiveLayerPriority } from './interactiveLayerPriority.ts';

test('resolveInteractiveLayerPriority prefers the most recently activated visible layer', () => {
  const priority = resolveInteractiveLayerPriority({
    showVisual: true,
    showIkHandles: false,
    showIkHandlesAlwaysOnTop: false,
    showCollision: true,
    showCollisionAlwaysOnTop: false,
    showOrigins: false,
    showOriginsOverlay: false,
    showJointAxes: false,
    showJointAxesOverlay: false,
    showCenterOfMass: true,
    showCoMOverlay: false,
    showInertia: false,
    showInertiaOverlay: false,
    activationOrder: {
      'ik-handle': 0,
      visual: 1,
      collision: 3,
      'origin-axes': 0,
      'joint-axis': 0,
      'center-of-mass': 2,
      inertia: 0,
    },
  });

  assert.deepEqual(priority, ['collision', 'center-of-mass', 'visual']);
});

test('resolveInteractiveLayerPriority promotes overlay layers ahead of newer non-overlay layers', () => {
  const priority = resolveInteractiveLayerPriority({
    showVisual: true,
    showIkHandles: false,
    showIkHandlesAlwaysOnTop: false,
    showCollision: true,
    showCollisionAlwaysOnTop: false,
    showOrigins: true,
    showOriginsOverlay: true,
    showJointAxes: false,
    showJointAxesOverlay: false,
    showCenterOfMass: false,
    showCoMOverlay: false,
    showInertia: false,
    showInertiaOverlay: false,
    activationOrder: {
      'ik-handle': 0,
      visual: 1,
      collision: 3,
      'origin-axes': 2,
      'joint-axis': 0,
      'center-of-mass': 0,
      inertia: 0,
    },
  });

  assert.deepEqual(priority, ['origin-axes', 'collision', 'visual']);
});

test('resolveInteractiveLayerPriority keeps collision overlays ahead of ik handles that only render on top', () => {
  const priority = resolveInteractiveLayerPriority({
    showVisual: true,
    showIkHandles: true,
    showIkHandlesAlwaysOnTop: true,
    showCollision: true,
    showCollisionAlwaysOnTop: true,
    showOrigins: false,
    showOriginsOverlay: false,
    showJointAxes: false,
    showJointAxesOverlay: false,
    showCenterOfMass: false,
    showCoMOverlay: false,
    showInertia: false,
    showInertiaOverlay: false,
    activationOrder: {
      'ik-handle': 1,
      visual: 1,
      collision: 1,
      'origin-axes': 0,
      'joint-axis': 0,
      'center-of-mass': 0,
      inertia: 0,
    },
  });

  assert.deepEqual(priority, ['collision', 'ik-handle', 'visual']);
});

test('resolveInteractiveLayerPriority favors axis helpers over ik handles when activation order ties', () => {
  const priority = resolveInteractiveLayerPriority({
    showVisual: true,
    showIkHandles: true,
    showIkHandlesAlwaysOnTop: true,
    showCollision: false,
    showCollisionAlwaysOnTop: false,
    showOrigins: true,
    showOriginsOverlay: false,
    showJointAxes: true,
    showJointAxesOverlay: false,
    showCenterOfMass: false,
    showCoMOverlay: false,
    showInertia: false,
    showInertiaOverlay: false,
    activationOrder: {
      'ik-handle': 1,
      visual: 1,
      collision: 0,
      'origin-axes': 1,
      'joint-axis': 1,
      'center-of-mass': 0,
      inertia: 0,
    },
  });

  assert.deepEqual(priority, ['joint-axis', 'origin-axes', 'ik-handle', 'visual']);
});
