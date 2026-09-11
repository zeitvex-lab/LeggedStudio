import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotFile } from '@/types';
import {
  createUsdSelectionBackgroundPrewarm,
  createUsdSelectionPrewarmHandler,
} from './usdSelectionPrewarm.ts';

test('USD selection prewarm is a no-op for non-USD files', () => {
  let mainThreadRuntimePrewarmCalls = 0;
  let offscreenRuntimePrewarmCalls = 0;
  let stageOpenPrewarmCalls = 0;

  const prewarm = createUsdSelectionPrewarmHandler({
    prewarmMainThreadRuntime: () => {
      mainThreadRuntimePrewarmCalls += 1;
    },
    prewarmOffscreenRuntime: () => {
      offscreenRuntimePrewarmCalls += 1;
    },
    prewarmStageOpen: () => {
      stageOpenPrewarmCalls += 1;
    },
    hasBlobBackedLargeUsdaInStageScope: () => false,
  });

  prewarm(
    {
      name: 'robots/demo/robot.urdf',
      format: 'urdf',
      content: '<robot />',
    },
    [],
    {},
  );

  assert.equal(mainThreadRuntimePrewarmCalls, 0);
  assert.equal(offscreenRuntimePrewarmCalls, 0);
  assert.equal(stageOpenPrewarmCalls, 0);
});

test('USD selection prewarm warms runtime and stage-open data together', () => {
  let mainThreadRuntimePrewarmCalls = 0;
  let offscreenRuntimePrewarmCalls = 0;
  const stageOpenCalls: Array<{
    file: Pick<RobotFile, 'name' | 'format'>;
    availableFiles: number;
    assetKeys: string[];
  }> = [];

  const prewarm = createUsdSelectionPrewarmHandler({
    prewarmMainThreadRuntime: () => {
      mainThreadRuntimePrewarmCalls += 1;
    },
    prewarmOffscreenRuntime: () => {
      offscreenRuntimePrewarmCalls += 1;
    },
    prewarmStageOpen: (file, availableFiles, assets) => {
      stageOpenCalls.push({
        file: { name: file.name, format: file.format },
        availableFiles: availableFiles.length,
        assetKeys: Object.keys(assets).sort(),
      });
    },
    hasBlobBackedLargeUsdaInStageScope: () => false,
  });

  prewarm(
    {
      name: 'robots/go2/usd/go2.usd',
      format: 'usd',
      content: '#usda 1.0',
      blobUrl: 'blob:go2-root',
    },
    [
      {
        name: 'robots/go2/usd/go2.usd',
        format: 'usd',
        content: '#usda 1.0',
        blobUrl: 'blob:go2-root',
      },
    ],
    {
      'robots/go2/textures/body.png': 'blob:body',
    },
  );

  assert.equal(mainThreadRuntimePrewarmCalls, 1);
  assert.equal(offscreenRuntimePrewarmCalls, 1);
  assert.deepEqual(stageOpenCalls, [
    {
      file: {
        name: 'robots/go2/usd/go2.usd',
        format: 'usd',
      },
      availableFiles: 1,
      assetKeys: ['robots/go2/textures/body.png'],
    },
  ]);
});

test('USD selection prewarm skips worker stage-open prewarm for blob-backed large USDA bundles', () => {
  let mainThreadRuntimePrewarmCalls = 0;
  let offscreenRuntimePrewarmCalls = 0;
  let stageOpenPrewarmCalls = 0;

  const prewarm = createUsdSelectionPrewarmHandler({
    prewarmMainThreadRuntime: () => {
      mainThreadRuntimePrewarmCalls += 1;
    },
    prewarmOffscreenRuntime: () => {
      offscreenRuntimePrewarmCalls += 1;
    },
    prewarmStageOpen: () => {
      stageOpenPrewarmCalls += 1;
    },
    hasBlobBackedLargeUsdaInStageScope: () => true,
  });

  prewarm(
    {
      name: 'g1_description/g1_23dof.usda',
      format: 'usd',
      content: '#usda 1.0\n(\n  subLayers = [@./configuration/g1_23dof_physics.usda@]\n)\n',
      blobUrl: 'blob:g1-root',
    },
    [
      {
        name: 'g1_description/configuration/g1_23dof_physics.usda',
        format: 'usd',
        content: '#usda 1.0\n(\n  subLayers = [@g1_23dof_base.usda@]\n)\n',
        blobUrl: 'blob:g1-physics',
      },
      {
        name: 'g1_description/configuration/g1_23dof_base.usda',
        format: 'usd',
        content: '',
        blobUrl: 'blob:g1-base',
      },
    ],
    {},
  );

  assert.equal(mainThreadRuntimePrewarmCalls, 1);
  assert.equal(offscreenRuntimePrewarmCalls, 1);
  assert.equal(stageOpenPrewarmCalls, 0);
});

test('USD selection prewarm skips runtime and stage-open prewarm when environment is unsupported', () => {
  let mainThreadRuntimePrewarmCalls = 0;
  let offscreenRuntimePrewarmCalls = 0;
  let stageOpenPrewarmCalls = 0;

  const prewarm = createUsdSelectionPrewarmHandler({
    prewarmMainThreadRuntime: () => {
      mainThreadRuntimePrewarmCalls += 1;
    },
    prewarmOffscreenRuntime: () => {
      offscreenRuntimePrewarmCalls += 1;
    },
    prewarmStageOpen: () => {
      stageOpenPrewarmCalls += 1;
    },
    hasBlobBackedLargeUsdaInStageScope: () => false,
    getRuntimeEnvironmentError: () => new Error('USD loading requires a secure context.'),
  });

  prewarm(
    {
      name: 'robots/go2/usd/go2.usd',
      format: 'usd',
      content: '#usda 1.0',
    },
    [],
    {},
  );

  assert.equal(mainThreadRuntimePrewarmCalls, 0);
  assert.equal(offscreenRuntimePrewarmCalls, 0);
  assert.equal(stageOpenPrewarmCalls, 0);
});

test('USD selection background prewarm logs loader failures without blocking callers', async () => {
  const file = {
    name: 'robots/demo/robot.usd',
    format: 'usd',
    content: '#usda 1.0',
  } as const;
  const error = new Error('selection prewarm load failed');
  const failures: unknown[] = [];

  const prewarm = createUsdSelectionBackgroundPrewarm({
    loadHandler: async () => {
      throw error;
    },
    logFailure: (_scope, failure) => {
      failures.push(failure);
      return failure instanceof Error ? failure : new Error(String(failure));
    },
  });

  assert.doesNotThrow(() => prewarm(file, [], {}));
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(failures, [error]);
});
