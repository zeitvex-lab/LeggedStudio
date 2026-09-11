import test from 'node:test';
import assert from 'node:assert/strict';

import {
  resolveUsdHoverCameraMotion,
  updateUsdHoverCameraMotionState,
} from './usdHoverCameraMotion.ts';

test('resolveUsdHoverCameraMotion suppresses hover processing while the camera is moving', () => {
  assert.deepEqual(resolveUsdHoverCameraMotion({
    pending: false,
    cameraMoved: true,
    hoverPointerButtons: 0,
    dragging: false,
  }), {
    pending: true,
    shouldMarkDirty: false,
    shouldSuppressProcessing: true,
  });
});

test('resolveUsdHoverCameraMotion marks hover dirty once the camera settles and the pointer is idle', () => {
  assert.deepEqual(resolveUsdHoverCameraMotion({
    pending: true,
    cameraMoved: false,
    hoverPointerButtons: 0,
    dragging: false,
  }), {
    pending: false,
    shouldMarkDirty: true,
    shouldSuppressProcessing: false,
  });
});

test('resolveUsdHoverCameraMotion keeps hover suspended while drag buttons remain pressed', () => {
  assert.deepEqual(resolveUsdHoverCameraMotion({
    pending: true,
    cameraMoved: false,
    hoverPointerButtons: 1,
    dragging: false,
  }), {
    pending: true,
    shouldMarkDirty: false,
    shouldSuppressProcessing: false,
  });
});

test('updateUsdHoverCameraMotionState persists pending camera motion across frames', () => {
  const pendingRef = { current: false };

  const duringMotion = updateUsdHoverCameraMotionState(pendingRef, {
    cameraMoved: true,
    hoverPointerButtons: 0,
    dragging: false,
  });
  assert.equal(pendingRef.current, true);
  assert.equal(duringMotion.shouldSuppressProcessing, true);

  const afterMotion = updateUsdHoverCameraMotionState(pendingRef, {
    cameraMoved: false,
    hoverPointerButtons: 0,
    dragging: false,
  });
  assert.equal(pendingRef.current, false);
  assert.equal(afterMotion.shouldMarkDirty, true);
});
