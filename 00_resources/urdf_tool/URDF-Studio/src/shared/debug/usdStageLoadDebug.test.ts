import test from 'node:test';
import assert from 'node:assert/strict';

import { getUsdStageLoadBaselineDurations, recordUsdStageLoadDebug } from './usdStageLoadDebug.ts';

test('getUsdStageLoadBaselineDurations returns the canonical five-step timings for a file', () => {
  const globalScope = globalThis as typeof globalThis & { window?: Window & typeof globalThis };
  const originalWindow = globalScope.window;
  const fakeWindow = {
    location: { search: '?regressionDebug=1' },
  } as Window & typeof globalThis;

  globalScope.window = fakeWindow;

  try {
    recordUsdStageLoadDebug({
      sourceFileName: 'robots/demo/usd/root.usd',
      step: 'ensure-runtime',
      status: 'resolved',
      timestamp: 1,
      durationMs: 12,
    });
    recordUsdStageLoadDebug({
      sourceFileName: 'robots/demo/usd/root.usd',
      step: 'prepare-stage-open-data',
      status: 'resolved',
      timestamp: 2,
      durationMs: 34,
    });
    recordUsdStageLoadDebug({
      sourceFileName: 'robots/demo/usd/root.usd',
      step: 'load-usd-stage',
      status: 'resolved',
      timestamp: 3,
      durationMs: 56,
    });
    recordUsdStageLoadDebug({
      sourceFileName: 'robots/demo/usd/root.usd',
      step: 'resolve-runtime-robot-data',
      status: 'resolved',
      timestamp: 4,
      durationMs: 78,
    });
    recordUsdStageLoadDebug({
      sourceFileName: 'robots/demo/usd/root.usd',
      step: 'ready',
      status: 'resolved',
      timestamp: 5,
      durationMs: 90,
    });
    recordUsdStageLoadDebug({
      sourceFileName: 'robots/other/usd/other.usd',
      step: 'ready',
      status: 'resolved',
      timestamp: 6,
      durationMs: 999,
    });

    assert.deepEqual(getUsdStageLoadBaselineDurations(fakeWindow, 'robots/demo/usd/root.usd'), {
      sourceFileName: 'robots/demo/usd/root.usd',
      steps: {
        'ensure-runtime': 12,
        'prepare-stage-open-data': 34,
        'load-usd-stage': 56,
        'resolve-runtime-robot-data': 78,
        ready: 90,
      },
    });
  } finally {
    if (originalWindow === undefined) {
      Reflect.deleteProperty(globalScope, 'window');
    } else {
      globalScope.window = originalWindow;
    }
  }
});

test('getUsdStageLoadBaselineDurations leaves missing baseline steps as null', () => {
  const targetWindow = {
    __usdStageLoadDebugHistory: [
      {
        sourceFileName: 'robots/demo/usd/root.usd',
        step: 'ensure-runtime',
        status: 'resolved',
        timestamp: 1,
        durationMs: 12,
      },
      {
        sourceFileName: 'robots/demo/usd/root.usd',
        step: 'load-usd-stage',
        status: 'rejected',
        timestamp: 2,
        durationMs: 44,
      },
    ],
  } as unknown as Window;

  assert.deepEqual(getUsdStageLoadBaselineDurations(targetWindow, 'robots/demo/usd/root.usd'), {
    sourceFileName: 'robots/demo/usd/root.usd',
    steps: {
      'ensure-runtime': 12,
      'prepare-stage-open-data': null,
      'load-usd-stage': null,
      'resolve-runtime-robot-data': null,
      ready: null,
    },
  });
});
