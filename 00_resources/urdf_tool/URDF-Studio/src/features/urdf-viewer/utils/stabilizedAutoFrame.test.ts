import test from 'node:test';
import assert from 'node:assert/strict';

import { scheduleStabilizedAutoFrame } from './stabilizedAutoFrame.ts';

type ScheduledTask = {
  cancelled: boolean;
  delayMs: number;
  run: () => void;
};

function createTestScheduler() {
  const tasks: ScheduledTask[] = [];

  return {
    tasks,
    scheduleTimeout(callback: () => void, delayMs: number) {
      const task: ScheduledTask = {
        cancelled: false,
        delayMs,
        run: callback,
      };
      tasks.push(task);
      return task;
    },
    clearScheduledTimeout(handle: unknown) {
      const task = handle as ScheduledTask | undefined;
      if (task) {
        task.cancelled = true;
      }
    },
  };
}

function runNextScheduledTask(tasks: ScheduledTask[]) {
  const task = tasks.find((candidate) => !candidate.cancelled);
  assert.ok(task, 'expected a scheduled task');
  task.cancelled = true;
  task.run();
}

test('scheduleStabilizedAutoFrame stops once the sampled bounds stay stable', () => {
  const scheduler = createTestScheduler();
  const stabilityKeys = ['frame-a', 'frame-a', 'frame-b'];
  const appliedKeys: string[] = [];
  const settledReasons: Array<'stable' | 'exhausted'> = [];

  scheduleStabilizedAutoFrame({
    sample: () => ({
      stabilityKey: stabilityKeys.shift() ?? null,
      state: null,
    }),
    applyFrame: ({ stabilityKey }) => {
      appliedKeys.push(String(stabilityKey));
      return true;
    },
    isActive: () => true,
    delays: [0, 80, 160],
    onSettled: (reason) => {
      settledReasons.push(reason);
    },
    scheduleTimeout: scheduler.scheduleTimeout,
    clearScheduledTimeout: scheduler.clearScheduledTimeout,
  });

  assert.equal(scheduler.tasks.length, 1);
  assert.equal(scheduler.tasks[0].delayMs, 0);

  runNextScheduledTask(scheduler.tasks);
  assert.equal(scheduler.tasks.length, 2);
  assert.equal(scheduler.tasks[1].delayMs, 80);

  runNextScheduledTask(scheduler.tasks);
  assert.deepEqual(appliedKeys, ['frame-a']);
  assert.deepEqual(settledReasons, ['stable']);
  assert.equal(
    scheduler.tasks.filter((task) => !task.cancelled).length,
    0,
  );
});

test('scheduleStabilizedAutoFrame applies only the final sample when retries are exhausted', () => {
  const scheduler = createTestScheduler();
  const appliedKeys: string[] = [];
  const settledReasons: Array<'stable' | 'exhausted'> = [];
  let sampleIndex = 0;

  scheduleStabilizedAutoFrame({
    sample: () => ({
      stabilityKey: `frame-${sampleIndex++}`,
      state: null,
    }),
    applyFrame: ({ stabilityKey }) => {
      appliedKeys.push(String(stabilityKey));
      return true;
    },
    isActive: () => true,
    delays: [0, 80, 160],
    onSettled: (reason) => {
      settledReasons.push(reason);
    },
    scheduleTimeout: scheduler.scheduleTimeout,
    clearScheduledTimeout: scheduler.clearScheduledTimeout,
  });

  runNextScheduledTask(scheduler.tasks);
  runNextScheduledTask(scheduler.tasks);
  runNextScheduledTask(scheduler.tasks);

  assert.deepEqual(appliedKeys, ['frame-2']);
  assert.deepEqual(settledReasons, ['exhausted']);
  assert.equal(
    scheduler.tasks.filter((task) => !task.cancelled).length,
    0,
  );
});

test('scheduleStabilizedAutoFrame clears pending retries when disposed', () => {
  const scheduler = createTestScheduler();

  const dispose = scheduleStabilizedAutoFrame({
    sample: () => ({
      stabilityKey: null,
      state: null,
    }),
    applyFrame: () => false,
    isActive: () => true,
    delays: [0, 80, 160],
    scheduleTimeout: scheduler.scheduleTimeout,
    clearScheduledTimeout: scheduler.clearScheduledTimeout,
  });

  runNextScheduledTask(scheduler.tasks);
  assert.equal(scheduler.tasks.filter((task) => !task.cancelled).length, 1);

  dispose();
  assert.equal(
    scheduler.tasks.filter((task) => !task.cancelled).length,
    0,
  );
});
