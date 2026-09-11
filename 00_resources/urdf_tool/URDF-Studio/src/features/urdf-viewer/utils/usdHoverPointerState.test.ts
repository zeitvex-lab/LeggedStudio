import test from 'node:test';
import assert from 'node:assert/strict';

import {
  clearUsdHoverPointerState,
  markUsdHoverRaycastDirty,
  shouldProcessUsdHoverRaycast,
  setUsdHoverPointerState,
  setUsdHoverPointerButtons,
  type UsdHoverPointerStateRefs,
} from './usdHoverPointerState.ts';

function createHoverRefs(): UsdHoverPointerStateRefs {
  return {
    hoverPointerLocalRef: { current: null },
    hoverPointerInsideRef: { current: false },
    hoverNeedsRaycastRef: { current: false },
    hoverPointerButtonsRef: { current: 0 },
  };
}

test('setUsdHoverPointerState marks hover refs and requests a render frame', () => {
  const refs = createHoverRefs();
  let frameRequests = 0;

  setUsdHoverPointerState(refs, { x: 12, y: 34 }, () => {
    frameRequests += 1;
  }, 1);

  assert.deepEqual(refs.hoverPointerLocalRef.current, { x: 12, y: 34 });
  assert.equal(refs.hoverPointerInsideRef.current, true);
  assert.equal(refs.hoverNeedsRaycastRef.current, true);
  assert.equal(refs.hoverPointerButtonsRef.current, 1);
  assert.equal(frameRequests, 1);
});

test('clearUsdHoverPointerState clears hover refs and requests a render frame', () => {
  const refs = createHoverRefs();
  refs.hoverPointerLocalRef.current = { x: 99, y: 77 };
  refs.hoverPointerInsideRef.current = true;
  refs.hoverNeedsRaycastRef.current = true;

  let frameRequests = 0;

  clearUsdHoverPointerState(refs, () => {
    frameRequests += 1;
  });

  assert.equal(refs.hoverPointerLocalRef.current, null);
  assert.equal(refs.hoverPointerInsideRef.current, false);
  assert.equal(refs.hoverNeedsRaycastRef.current, false);
  assert.equal(refs.hoverPointerButtonsRef.current, 0);
  assert.equal(frameRequests, 1);
});

test('markUsdHoverRaycastDirty marks raycast work and requests a render frame', () => {
  const refs = createHoverRefs();
  let frameRequests = 0;

  markUsdHoverRaycastDirty(refs.hoverNeedsRaycastRef, () => {
    frameRequests += 1;
  });

  assert.equal(refs.hoverNeedsRaycastRef.current, true);
  assert.equal(frameRequests, 1);
});

test('setUsdHoverPointerButtons updates the pressed-button state and requests a render frame', () => {
  const refs = createHoverRefs();
  let frameRequests = 0;

  setUsdHoverPointerButtons(refs.hoverPointerButtonsRef, 1, () => {
    frameRequests += 1;
  });

  assert.equal(refs.hoverPointerButtonsRef.current, 1);
  assert.equal(frameRequests, 1);
});

test('shouldProcessUsdHoverRaycast blocks hover while a pointer button stays pressed', () => {
  const shouldProcess = shouldProcessUsdHoverRaycast({
    hoverPointerInside: true,
    pointer: { x: 12, y: 34 },
    hoverNeedsRaycast: true,
    hoverPointerButtons: 1,
    justSelected: false,
    dragging: false,
  });

  assert.equal(shouldProcess, false);
});

test('shouldProcessUsdHoverRaycast allows hover only when pointer is idle and dirty', () => {
  const shouldProcess = shouldProcessUsdHoverRaycast({
    hoverPointerInside: true,
    pointer: { x: 12, y: 34 },
    hoverNeedsRaycast: true,
    hoverPointerButtons: 0,
    justSelected: false,
    dragging: false,
  });

  assert.equal(shouldProcess, true);
});
