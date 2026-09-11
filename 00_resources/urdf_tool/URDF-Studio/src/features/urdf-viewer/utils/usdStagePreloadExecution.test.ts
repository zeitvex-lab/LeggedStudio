import test from 'node:test';
import assert from 'node:assert/strict';

import {
  preloadUsdStageEntries,
  resolveUsdPreloadConcurrency,
  splitUsdStagePreloadEntries,
} from './usdStagePreloadExecution.ts';

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

test('splitUsdStagePreloadEntries keeps the root stage entry separate from dependency entries', () => {
  const result = splitUsdStagePreloadEntries('/robots/go2/usd/go2.usd', [
    { path: '/robots/go2/textures/body.png' },
    { path: '/robots/go2/usd/configuration/go2_description_base.usd' },
    { path: '/robots/go2/usd/go2.usd' },
  ]);

  assert.deepEqual(
    result.dependencyEntries.map((entry) => entry.path),
    [
      '/robots/go2/textures/body.png',
      '/robots/go2/usd/configuration/go2_description_base.usd',
    ],
  );
  assert.equal(result.rootEntry?.path, '/robots/go2/usd/go2.usd');
});

test('resolveUsdPreloadConcurrency caps preload fan-out at 10 writes', () => {
  assert.equal(resolveUsdPreloadConcurrency(64), 10);
  assert.equal(resolveUsdPreloadConcurrency(1), 2);
});

test('preloadUsdStageEntries parallelizes dependency writes but keeps the root stage write last', async () => {
  const events: string[] = [];
  let activeWrites = 0;
  let peakActiveWrites = 0;

  await preloadUsdStageEntries({
    stageSourcePath: '/robots/go2/usd/go2.usd',
    entries: [
      { path: '/robots/go2/textures/body.png', delayMs: 20 },
      { path: '/robots/go2/usd/configuration/go2_description_base.usd', delayMs: 20 },
      { path: '/robots/go2/usd/go2.usd', delayMs: 0 },
    ],
    concurrency: 2,
    isActive: () => true,
    preloadEntry: async (entry) => {
      activeWrites += 1;
      peakActiveWrites = Math.max(peakActiveWrites, activeWrites);
      events.push(`start:${entry.path}`);
      await wait(entry.delayMs);
      events.push(`finish:${entry.path}`);
      activeWrites -= 1;
    },
  });

  assert.equal(peakActiveWrites, 2);

  const rootStartIndex = events.indexOf('start:/robots/go2/usd/go2.usd');
  const lastDependencyFinishIndex = Math.max(
    events.indexOf('finish:/robots/go2/textures/body.png'),
    events.indexOf('finish:/robots/go2/usd/configuration/go2_description_base.usd'),
  );

  assert.ok(rootStartIndex > lastDependencyFinishIndex);
});

test('preloadUsdStageEntries skips the deferred root write once the load becomes inactive', async () => {
  const loadedPaths: string[] = [];
  let active = true;

  await preloadUsdStageEntries({
    stageSourcePath: '/robots/go2/usd/go2.usd',
    entries: [
      { path: '/robots/go2/usd/configuration/go2_description_base.usd' },
      { path: '/robots/go2/usd/go2.usd' },
    ],
    concurrency: 1,
    isActive: () => active,
    preloadEntry: async (entry) => {
      loadedPaths.push(entry.path);
      active = false;
    },
  });

  assert.deepEqual(loadedPaths, ['/robots/go2/usd/configuration/go2_description_base.usd']);
});
