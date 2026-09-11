import assert from 'node:assert/strict';
import test from 'node:test';

import { clearControlPointerState, hasControlPointerIntent } from './pointerState.ts';

test('hasControlPointerIntent detects an active gizmo hover axis', () => {
  const controls = {
    dragging: false,
    axis: 'Z',
    userData: {},
  };

  assert.equal(hasControlPointerIntent(controls), true);
});

test('hasControlPointerIntent detects a cached visible-axis hit before drag begins', () => {
  const controls = {
    dragging: false,
    axis: null,
    userData: {
      urdfLastVisibleAxisHit: {
        axis: 'Y',
        x: 0.12,
        y: -0.08,
      },
    },
  };

  assert.equal(hasControlPointerIntent(controls), true);
});

test('hasControlPointerIntent ignores idle controls with no active axis', () => {
  const controls = {
    dragging: false,
    axis: null,
    userData: {
      urdfLastVisibleAxisHit: {
        axis: null,
        x: 0.12,
        y: -0.08,
      },
    },
  };

  assert.equal(hasControlPointerIntent(controls), false);
});

test('clearControlPointerState clears the idle axis and visible-hit cache', () => {
  const controls = {
    dragging: false,
    axis: 'X',
    userData: {
      urdfLastVisibleAxisHit: {
        axis: 'X',
        x: 0.25,
        y: -0.5,
      },
    },
  };

  clearControlPointerState(controls);

  assert.equal(controls.axis, null);
  assert.equal('urdfLastVisibleAxisHit' in controls.userData, false);
});

test('clearControlPointerState keeps the active drag axis intact while still clearing stale cache', () => {
  const controls = {
    dragging: true,
    axis: 'Y',
    userData: {
      urdfLastVisibleAxisHit: {
        axis: 'Y',
        x: 0.1,
        y: 0.2,
      },
    },
  };

  clearControlPointerState(controls);

  assert.equal(controls.axis, 'Y');
  assert.equal('urdfLastVisibleAxisHit' in controls.userData, false);
});
