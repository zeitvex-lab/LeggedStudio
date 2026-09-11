import test from 'node:test';
import assert from 'node:assert/strict';

import { scheduleUsdResolvedRobotRepublishAfterWarmup } from './usdResolvedRobotWarmup.ts';

function createDeferred() {
  let resolve!: () => void;
  let reject!: (reason?: unknown) => void;

  const promise = new Promise<void>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}

test('scheduleUsdResolvedRobotRepublishAfterWarmup republishes after all warmups settle', async () => {
  const scheduledFrames: Array<() => void> = [];
  const events: string[] = [];
  const first = createDeferred();
  const second = createDeferred();

  scheduleUsdResolvedRobotRepublishAfterWarmup({
    isActive: () => true,
    requestAnimationFrame: (callback) => {
      scheduledFrames.push(callback);
      return 1;
    },
    startWarmups: () => {
      events.push('start');
      return [first.promise, second.promise];
    },
    onSettled: () => {
      events.push('publish');
    },
  });

  assert.equal(events.length, 0);
  assert.equal(scheduledFrames.length, 1);

  scheduledFrames[0]();
  assert.deepEqual(events, ['start']);

  first.resolve();
  await Promise.resolve();
  assert.deepEqual(events, ['start']);

  second.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(events, ['start', 'publish']);
});

test('scheduleUsdResolvedRobotRepublishAfterWarmup aborts when the stage becomes inactive before publish', async () => {
  const scheduledFrames: Array<() => void> = [];
  let active = true;
  let publishCount = 0;
  const warmup = createDeferred();

  scheduleUsdResolvedRobotRepublishAfterWarmup({
    isActive: () => active,
    requestAnimationFrame: (callback) => {
      scheduledFrames.push(callback);
      return 1;
    },
    startWarmups: () => [warmup.promise],
    onSettled: () => {
      publishCount += 1;
    },
  });

  scheduledFrames[0]();
  active = false;
  warmup.resolve();
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(publishCount, 0);
});

test('scheduleUsdResolvedRobotRepublishAfterWarmup tolerates rejected warmups', async () => {
  const scheduledFrames: Array<() => void> = [];
  let publishCount = 0;
  const warmup = createDeferred();

  scheduleUsdResolvedRobotRepublishAfterWarmup({
    isActive: () => true,
    requestAnimationFrame: (callback) => {
      scheduledFrames.push(callback);
      return 1;
    },
    startWarmups: () => [warmup.promise],
    onSettled: () => {
      publishCount += 1;
    },
  });

  scheduledFrames[0]();
  warmup.reject(new Error('warmup failed'));
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(publishCount, 1);
});

test('scheduleUsdResolvedRobotRepublishAfterWarmup does not synchronously publish when warmup setup throws', async () => {
  const scheduledFrames: Array<() => void> = [];
  let publishCount = 0;

  scheduleUsdResolvedRobotRepublishAfterWarmup({
    isActive: () => true,
    requestAnimationFrame: (callback) => {
      scheduledFrames.push(callback);
      return 1;
    },
    startWarmups: () => {
      throw new Error('setup failed');
    },
    onSettled: () => {
      publishCount += 1;
    },
  });

  scheduledFrames[0]();
  assert.equal(publishCount, 0);

  await Promise.resolve();
  await Promise.resolve();

  assert.equal(publishCount, 1);
});
