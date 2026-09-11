import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveUsdOffscreenFullscreenHtmlPosition } from './usdOffscreenHtmlPosition.ts';

test('resolveUsdOffscreenFullscreenHtmlPosition anchors fullscreen overlay to the canvas center', () => {
  assert.deepEqual(
    resolveUsdOffscreenFullscreenHtmlPosition(null, null, {
      width: 1393,
      height: 2009,
    }),
    [696.5, 1004.5],
  );
});
