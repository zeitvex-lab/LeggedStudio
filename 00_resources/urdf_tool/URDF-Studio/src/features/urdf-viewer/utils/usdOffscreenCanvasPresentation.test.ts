import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveUsdOffscreenCanvasPresentation } from './usdOffscreenCanvasPresentation.ts';

test('resolveUsdOffscreenCanvasPresentation keeps the USD layer transparent over WorkspaceCanvas', () => {
  assert.deepEqual(resolveUsdOffscreenCanvasPresentation('light'), {
    alpha: true,
    backgroundColor: '#f3f4f6',
    clearAlpha: 0,
    cssBackgroundColor: 'transparent',
    sceneBackgroundColor: null,
  });
  assert.deepEqual(resolveUsdOffscreenCanvasPresentation('dark'), {
    alpha: true,
    backgroundColor: '#1f1f1f',
    clearAlpha: 0,
    cssBackgroundColor: 'transparent',
    sceneBackgroundColor: null,
  });
});
