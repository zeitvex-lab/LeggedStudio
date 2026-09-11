import assert from 'node:assert/strict';
import test from 'node:test';

import {
  scheduleUsdPostReadyBackgroundTask,
  shouldAutoPrepareUsdPostReadyExportCache,
  USD_POST_READY_AUTO_EXPORT_CACHE_POSITION_LIMIT,
} from './usdPostReadyBackgroundTask.ts';

function createScheduler() {
  let nextHandle = 1;
  const timeouts = new Map<number, () => void>();
  const idleCallbacks = new Map<number, () => void>();

  return {
    scheduler: {
      setTimeout(callback: () => void) {
        const handle = nextHandle++;
        timeouts.set(handle, callback);
        return handle;
      },
      clearTimeout(handle: number) {
        timeouts.delete(handle);
      },
      requestIdleCallback(callback: () => void) {
        const handle = nextHandle++;
        idleCallbacks.set(handle, callback);
        return handle;
      },
      cancelIdleCallback(handle: number) {
        idleCallbacks.delete(handle);
      },
    },
    flushNextTimeout() {
      const [handle, callback] = timeouts.entries().next().value ?? [];
      if (!handle || !callback) return false;
      timeouts.delete(handle);
      callback();
      return true;
    },
    flushNextIdle() {
      const [handle, callback] = idleCallbacks.entries().next().value ?? [];
      if (!handle || !callback) return false;
      idleCallbacks.delete(handle);
      callback();
      return true;
    },
    counts() {
      return {
        timeouts: timeouts.size,
        idleCallbacks: idleCallbacks.size,
      };
    },
  };
}

test('scheduleUsdPostReadyBackgroundTask waits for delay and idle before running', () => {
  const harness = createScheduler();
  let runs = 0;

  scheduleUsdPostReadyBackgroundTask(() => {
    runs += 1;
  }, { scheduler: harness.scheduler });

  assert.equal(runs, 0);
  assert.deepEqual(harness.counts(), { timeouts: 1, idleCallbacks: 0 });
  assert.equal(harness.flushNextTimeout(), true);
  assert.equal(runs, 0);
  assert.deepEqual(harness.counts(), { timeouts: 0, idleCallbacks: 1 });
  assert.equal(harness.flushNextIdle(), true);
  assert.equal(runs, 1);
});

test('scheduleUsdPostReadyBackgroundTask cancellation prevents delayed work', () => {
  const harness = createScheduler();
  let runs = 0;

  const cancel = scheduleUsdPostReadyBackgroundTask(() => {
    runs += 1;
  }, { scheduler: harness.scheduler });

  cancel();
  assert.equal(harness.flushNextTimeout(), false);
  assert.equal(harness.flushNextIdle(), false);
  assert.equal(runs, 0);
});

test('shouldAutoPrepareUsdPostReadyExportCache skips large USD snapshots', () => {
  assert.equal(
    shouldAutoPrepareUsdPostReadyExportCache({
      buffers: {
        positions: { length: USD_POST_READY_AUTO_EXPORT_CACHE_POSITION_LIMIT },
      },
    }),
    true,
  );
  assert.equal(
    shouldAutoPrepareUsdPostReadyExportCache({
      buffers: {
        positions: { length: USD_POST_READY_AUTO_EXPORT_CACHE_POSITION_LIMIT + 1 },
      },
    }),
    false,
  );
});
