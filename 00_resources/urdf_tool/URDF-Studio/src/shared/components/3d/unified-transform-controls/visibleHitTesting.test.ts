import assert from 'node:assert/strict';
import test from 'node:test';

import { patchVisiblePointerDownFallback } from './visibleHitTesting.ts';

type VisibleAxisCacheEntry = {
  axis: 'X' | 'Y' | 'Z' | null;
  x: number;
  y: number;
};

function createControls() {
  let pointerDownCalls = 0;

  return {
    controls: {
      object: {},
      dragging: false,
      mode: 'translate',
      axis: null as 'X' | 'Y' | 'Z' | null,
      userData: {} as {
        urdfLastVisibleAxisHit?: VisibleAxisCacheEntry;
        urdfVisiblePointerDownFallbackPatched?: boolean;
        urdfUseVisibleHitFallback?: boolean;
      },
      pointerDown: (_pointer?: { x: number; y: number; button?: number }) => {
        pointerDownCalls += 1;
      },
    },
    getPointerDownCalls: () => pointerDownCalls,
  };
}

test('patchVisiblePointerDownFallback reuses the cached axis when the pointer position matches', () => {
  const { controls, getPointerDownCalls } = createControls();
  controls.userData.urdfUseVisibleHitFallback = true;
  controls.userData.urdfLastVisibleAxisHit = {
    axis: 'X',
    x: 0.25,
    y: -0.4,
  };

  patchVisiblePointerDownFallback(controls);
  controls.pointerDown({ x: 0.25, y: -0.4, button: 0 });

  assert.equal(controls.axis, 'X');
  assert.equal(getPointerDownCalls(), 1);
});

test('patchVisiblePointerDownFallback invalidates the cached axis after the pointer moves', () => {
  const { controls, getPointerDownCalls } = createControls();
  controls.userData.urdfUseVisibleHitFallback = true;
  controls.userData.urdfLastVisibleAxisHit = {
    axis: 'Y',
    x: 0.1,
    y: 0.1,
  };

  patchVisiblePointerDownFallback(controls);
  controls.pointerDown({ x: 0.5, y: 0.5, button: 0 });

  assert.equal(controls.axis, null);
  assert.equal(getPointerDownCalls(), 0);
});

test('patchVisiblePointerDownFallback preserves stock gizmo pointerDown behavior when fallback is disabled', () => {
  const { controls, getPointerDownCalls } = createControls();
  controls.userData.urdfUseVisibleHitFallback = false;

  patchVisiblePointerDownFallback(controls);
  controls.pointerDown({ x: 0.5, y: 0.5, button: 0 });

  assert.equal(controls.axis, null);
  assert.equal(getPointerDownCalls(), 1);
});
