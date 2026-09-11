import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isCanvasLayoutTransitionProperty,
  shouldStartCanvasResizeFrameloop,
} from './CanvasResizeSync';

test('isCanvasLayoutTransitionProperty matches sidebar width transitions', () => {
  assert.equal(isCanvasLayoutTransitionProperty('width'), true);
  assert.equal(isCanvasLayoutTransitionProperty('min-width'), true);
  assert.equal(isCanvasLayoutTransitionProperty('flex-basis'), true);
  assert.equal(isCanvasLayoutTransitionProperty('opacity'), false);
  assert.equal(isCanvasLayoutTransitionProperty('transform'), false);
});

test('shouldStartCanvasResizeFrameloop avoids restarting an active resize loop', () => {
  assert.equal(shouldStartCanvasResizeFrameloop(false), true);
  assert.equal(shouldStartCanvasResizeFrameloop(true), false);
});
