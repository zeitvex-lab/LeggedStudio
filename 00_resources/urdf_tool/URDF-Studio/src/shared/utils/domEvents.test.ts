import assert from 'node:assert/strict';
import test from 'node:test';

import { JSDOM } from 'jsdom';

import { attachContextMenuBlocker } from './domEvents.ts';

test('attachContextMenuBlocker prevents the browser context menu and restores default behavior after cleanup', () => {
  const dom = new JSDOM('<!doctype html><html><body><canvas id="canvas"></canvas></body></html>', {
    url: 'http://localhost/',
  });

  const canvas = dom.window.document.getElementById('canvas');
  assert.ok(canvas, 'canvas should exist');

  const cleanup = attachContextMenuBlocker(canvas);

  const blockedEvent = new dom.window.MouseEvent('contextmenu', {
    bubbles: true,
    cancelable: true,
  });

  canvas.dispatchEvent(blockedEvent);

  assert.equal(blockedEvent.defaultPrevented, true);

  cleanup();

  const restoredEvent = new dom.window.MouseEvent('contextmenu', {
    bubbles: true,
    cancelable: true,
  });

  canvas.dispatchEvent(restoredEvent);

  assert.equal(restoredEvent.defaultPrevented, false);
});
