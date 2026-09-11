import assert from 'node:assert/strict';
import test from 'node:test';

import { schedulePostReadyBackgroundTask } from './postReadyBackgroundTask.ts';

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

test('schedulePostReadyBackgroundTask waits for delay and idle before running', () => {
  const harness = createScheduler();
  let runs = 0;

  schedulePostReadyBackgroundTask(() => {
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

test('schedulePostReadyBackgroundTask cancellation prevents delayed work', () => {
  const harness = createScheduler();
  let runs = 0;

  const cancel = schedulePostReadyBackgroundTask(() => {
    runs += 1;
  }, { scheduler: harness.scheduler });

  cancel();
  assert.equal(harness.flushNextTimeout(), false);
  assert.equal(harness.flushNextIdle(), false);
  assert.equal(runs, 0);
});
