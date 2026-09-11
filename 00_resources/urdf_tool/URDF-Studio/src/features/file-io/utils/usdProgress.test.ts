import test from 'node:test';
import assert from 'node:assert/strict';

import {
  advanceUsdProgress,
  createUsdProgressTracker,
  isUsdExportRunningInWorkerScope,
  normalizeUsdProgressLabel,
  yieldToMainThread,
} from './usdProgress.ts';

test('normalizeUsdProgressLabel trims values and falls back for blank labels', () => {
  assert.equal(normalizeUsdProgressLabel('  mesh_0  ', 'asset'), 'mesh_0');
  assert.equal(normalizeUsdProgressLabel('   ', 'asset'), 'asset');
  assert.equal(normalizeUsdProgressLabel(undefined, 'asset'), 'asset');
});

test('createUsdProgressTracker emits initial progress and advanceUsdProgress clamps at total', () => {
  const events: Array<{ phase: string; completed: number; total: number; label?: string }> = [];
  const tracker = createUsdProgressTracker('scene', 2, (progress) => {
    events.push(progress);
  });

  advanceUsdProgress(tracker, 'root');
  advanceUsdProgress(tracker, 'looks');
  advanceUsdProgress(tracker, 'overflow');

  assert.deepEqual(events, [
    { phase: 'scene', completed: 0, total: 2 },
    { phase: 'scene', completed: 1, total: 2, label: 'root' },
    { phase: 'scene', completed: 2, total: 2, label: 'looks' },
    { phase: 'scene', completed: 2, total: 2, label: 'overflow' },
  ]);
});

test('isUsdExportRunningInWorkerScope detects mocked worker globals', () => {
  const originalWorkerGlobalScope = globalThis.WorkerGlobalScope;
  const originalPrototype = Object.getPrototypeOf(globalThis);

  class MockWorkerGlobalScope {}

  try {
    Object.defineProperty(globalThis, 'WorkerGlobalScope', {
      configurable: true,
      value: MockWorkerGlobalScope,
    });
    Object.setPrototypeOf(globalThis, MockWorkerGlobalScope.prototype);

    assert.equal(isUsdExportRunningInWorkerScope(), true);
  } finally {
    if (originalWorkerGlobalScope === undefined) {
      Reflect.deleteProperty(globalThis, 'WorkerGlobalScope');
    } else {
      Object.defineProperty(globalThis, 'WorkerGlobalScope', {
        configurable: true,
        value: originalWorkerGlobalScope,
      });
    }
    Object.setPrototypeOf(globalThis, originalPrototype);
  }
});

test('yieldToMainThread returns immediately inside a worker scope', async () => {
  const originalWorkerGlobalScope = globalThis.WorkerGlobalScope;
  const originalPrototype = Object.getPrototypeOf(globalThis);
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalSetTimeout = globalThis.setTimeout;

  class MockWorkerGlobalScope {}

  let requestAnimationFrameCalls = 0;
  let setTimeoutCalls = 0;

  try {
    Object.defineProperty(globalThis, 'WorkerGlobalScope', {
      configurable: true,
      value: MockWorkerGlobalScope,
    });
    Object.setPrototypeOf(globalThis, MockWorkerGlobalScope.prototype);

    globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      requestAnimationFrameCalls += 1;
      callback(0);
      return 1;
    }) as typeof globalThis.requestAnimationFrame;
    globalThis.setTimeout = ((callback: TimerHandler) => {
      setTimeoutCalls += 1;
      if (typeof callback === 'function') {
        callback();
      }
      return 1 as unknown as ReturnType<typeof setTimeout>;
    }) as unknown as typeof globalThis.setTimeout;

    await yieldToMainThread();

    assert.equal(requestAnimationFrameCalls, 0);
    assert.equal(setTimeoutCalls, 0);
  } finally {
    if (originalWorkerGlobalScope === undefined) {
      Reflect.deleteProperty(globalThis, 'WorkerGlobalScope');
    } else {
      Object.defineProperty(globalThis, 'WorkerGlobalScope', {
        configurable: true,
        value: originalWorkerGlobalScope,
      });
    }
    Object.setPrototypeOf(globalThis, originalPrototype);
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.setTimeout = originalSetTimeout;
  }
});
