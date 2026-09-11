import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getLatestVisualizerCollisionLoadDebugEntry,
  getVisualizerCollisionLoadDebugHistory,
  recordVisualizerCollisionLoadDebug,
} from './visualizerCollisionLoadDebug.ts';

test('visualizer collision load debug records and filters session history by signature', () => {
  const globalScope = globalThis as typeof globalThis & { window?: Window & typeof globalThis };
  const originalWindow = globalScope.window;
  const fakeWindow = {
    location: { search: '?regressionDebug=1' },
  } as Window & typeof globalThis;

  globalScope.window = fakeWindow;

  try {
    recordVisualizerCollisionLoadDebug({
      sessionId: 'session-a',
      signature: 'sig-a',
      phase: 'show-requested',
      timestamp: 1,
      detail: { totalComponentCount: 3 },
    });
    recordVisualizerCollisionLoadDebug({
      sessionId: 'session-a',
      signature: 'sig-a',
      phase: 'reveal-progress',
      timestamp: 2,
      durationMs: 25,
      detail: { revealedComponentCount: 1 },
    });
    recordVisualizerCollisionLoadDebug({
      sessionId: 'session-b',
      signature: 'sig-b',
      phase: 'reveal-complete',
      timestamp: 3,
      durationMs: 11,
    });

    assert.deepEqual(
      getVisualizerCollisionLoadDebugHistory(fakeWindow, 'sig-a').map((entry) => entry.phase),
      ['show-requested', 'reveal-progress'],
    );
    assert.deepEqual(
      getLatestVisualizerCollisionLoadDebugEntry(fakeWindow, 'reveal-progress', 'sig-a'),
      {
        sessionId: 'session-a',
        signature: 'sig-a',
        phase: 'reveal-progress',
        timestamp: 2,
        durationMs: 25,
        detail: { revealedComponentCount: 1 },
      },
    );
  } finally {
    if (originalWindow === undefined) {
      Reflect.deleteProperty(globalScope, 'window');
    } else {
      globalScope.window = originalWindow;
    }
  }
});
