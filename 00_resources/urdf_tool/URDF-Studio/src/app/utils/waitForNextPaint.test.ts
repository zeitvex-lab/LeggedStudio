import assert from 'node:assert/strict';
import test from 'node:test';

import { waitForAnimationFrame } from './waitForAnimationFrame.ts';
import { waitForNextPaint } from './waitForNextPaint.ts';

test('waitForNextPaint resolves after two animation frames when RAF is available', async () => {
  const originalWindow = globalThis.window;
  const rafCallbacks: FrameRequestCallback[] = [];

  (
    globalThis as typeof globalThis & {
      window: Window & typeof globalThis;
    }
  ).window = {
    requestAnimationFrame: (callback: FrameRequestCallback) => {
      rafCallbacks.push(callback);
      return rafCallbacks.length;
    },
  } as unknown as Window & typeof globalThis;

  let resolved = false;
  const waitPromise = waitForNextPaint().then(() => {
    resolved = true;
  });

  await Promise.resolve();
  assert.equal(rafCallbacks.length, 1);
  assert.equal(resolved, false);

  const firstFrame = rafCallbacks.shift();
  assert.ok(firstFrame);
  firstFrame(0);

  await Promise.resolve();
  assert.equal(rafCallbacks.length, 1);
  assert.equal(resolved, false);

  const secondFrame = rafCallbacks.shift();
  assert.ok(secondFrame);
  secondFrame(16);

  await waitPromise;
  assert.equal(resolved, true);

  if (originalWindow === undefined) {
    Reflect.deleteProperty(globalThis, 'window');
  } else {
    (globalThis as typeof globalThis & { window: Window }).window = originalWindow;
  }
});

test('waitForNextPaint resolves immediately when requestAnimationFrame is unavailable', async () => {
  const originalWindow = globalThis.window;
  Reflect.deleteProperty(globalThis, 'window');

  await waitForNextPaint();

  if (originalWindow !== undefined) {
    (globalThis as typeof globalThis & { window: Window }).window = originalWindow;
  }
});

test('waitForAnimationFrame resolves after one animation frame when RAF is available', async () => {
  const originalWindow = globalThis.window;
  const rafCallbacks: FrameRequestCallback[] = [];

  (
    globalThis as typeof globalThis & {
      window: Window & typeof globalThis;
    }
  ).window = {
    requestAnimationFrame: (callback: FrameRequestCallback) => {
      rafCallbacks.push(callback);
      return rafCallbacks.length;
    },
  } as unknown as Window & typeof globalThis;

  let resolved = false;
  const waitPromise = waitForAnimationFrame().then(() => {
    resolved = true;
  });

  await Promise.resolve();
  assert.equal(rafCallbacks.length, 1);
  assert.equal(resolved, false);

  const frame = rafCallbacks.shift();
  assert.ok(frame);
  frame(0);

  await waitPromise;
  assert.equal(resolved, true);

  if (originalWindow === undefined) {
    Reflect.deleteProperty(globalThis, 'window');
  } else {
    (globalThis as typeof globalThis & { window: Window }).window = originalWindow;
  }
});
