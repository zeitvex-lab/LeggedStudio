import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotFile } from '@/types';
import {
  buildPreparedUsdStageOpenCacheKey,
  clearPreparedUsdStageOpenCache,
  loadPreparedUsdStageOpenDataInline,
  loadPreparedUsdStageOpenDataFromWorker,
  loadPreparedUsdStageOpenDataCached,
} from './preparedUsdStageOpenCache.ts';

const demoSourceFile: Pick<RobotFile, 'name' | 'content' | 'blobUrl'> = {
  name: 'robots/go2/usd/go2.usd',
  content: 'demo-stage',
  blobUrl: undefined,
};

const demoAvailableFiles: Array<Pick<RobotFile, 'name' | 'content' | 'blobUrl' | 'format'>> = [
  {
    name: 'robots/go2/usd/go2.usd',
    content: 'demo-stage',
    blobUrl: undefined,
    format: 'usd',
  },
];

const demoAssets = {
  'robots/go2/usd/go2.usd': 'blob:go2-root',
};

test.afterEach(() => {
  clearPreparedUsdStageOpenCache();
});

test('loadPreparedUsdStageOpenDataCached reuses the same prepared preload payload for repeated opens', async () => {
  let loadCount = 0;
  const loader = async () => {
    loadCount += 1;
    return {
      stageSourcePath: '/robots/go2/usd/go2.usd',
      criticalDependencyPaths: ['/robots/go2/usd/configuration/go2_description_base.usd'],
      preloadFiles: [
        {
          path: '/robots/go2/usd/go2.usd',
          blob: new Blob(['go2-root']),
          error: null,
        },
      ],
    };
  };

  const firstResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    loader,
  );
  const secondResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    loader,
  );

  assert.equal(loadCount, 1);
  assert.strictEqual(secondResult, firstResult);
});

test('loadPreparedUsdStageOpenDataCached drops incomplete root-stage results so a later open can retry', async () => {
  let loadCount = 0;

  const firstResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    async () => {
      loadCount += 1;
      return {
        stageSourcePath: '/robots/go2/usd/go2.usd',
        criticalDependencyPaths: [],
        preloadFiles: [
          {
            path: '/robots/go2/usd/go2.usd',
            blob: null,
            error: 'missing-root',
          },
        ],
      };
    },
  );

  const secondResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    async () => {
      loadCount += 1;
      return {
        stageSourcePath: '/robots/go2/usd/go2.usd',
        criticalDependencyPaths: [],
        preloadFiles: [
          {
            path: '/robots/go2/usd/go2.usd',
            blob: new Blob(['go2-root']),
            error: null,
          },
        ],
      };
    },
  );

  assert.equal(loadCount, 2);
  assert.equal(firstResult.preloadFiles[0]?.blob, null);
  assert.ok(secondResult.preloadFiles[0]?.blob instanceof Blob);
});

test('loadPreparedUsdStageOpenDataCached keeps worker-hydrated root bytes as a valid cached payload', async () => {
  let loadCount = 0;
  const rootBytes = new TextEncoder().encode('go2-root');

  const firstResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    async () => {
      loadCount += 1;
      return {
        stageSourcePath: '/robots/go2/usd/go2.usd',
        criticalDependencyPaths: [],
        preloadFiles: [
          {
            path: '/robots/go2/usd/go2.usd',
            blob: null,
            bytes: rootBytes,
            mimeType: 'application/octet-stream',
            error: null,
          },
        ],
      };
    },
  );

  const secondResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    async () => {
      loadCount += 1;
      return {
        stageSourcePath: '/robots/go2/usd/go2.usd',
        criticalDependencyPaths: [],
        preloadFiles: [],
      };
    },
  );

  assert.equal(loadCount, 1);
  assert.strictEqual(secondResult, firstResult);
  assert.deepEqual(
    Array.from(new Uint8Array(firstResult.preloadFiles[0]!.bytes!)),
    Array.from(rootBytes),
  );
});

test('loadPreparedUsdStageOpenDataCached reuses semantically identical inputs even when object references change', async () => {
  let loadCount = 0;
  const loader = async () => {
    loadCount += 1;
    return {
      stageSourcePath: '/robots/go2/usd/go2.usd',
      criticalDependencyPaths: ['/robots/go2/usd/configuration/go2_description_base.usd'],
      preloadFiles: [
        {
          path: '/robots/go2/usd/go2.usd',
          blob: new Blob(['go2-root']),
          error: null,
        },
      ],
    };
  };

  const firstResult = await loadPreparedUsdStageOpenDataCached(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    loader,
  );
  const secondResult = await loadPreparedUsdStageOpenDataCached(
    {
      ...demoSourceFile,
    },
    demoAvailableFiles.map((file) => ({ ...file })),
    {
      ...demoAssets,
    },
    loader,
  );

  assert.equal(loadCount, 1);
  assert.strictEqual(secondResult, firstResult);
});

test('worker and inline stage-open caches stay isolated for the same USD input', async () => {
  let workerLoadCount = 0;
  let inlineLoadCount = 0;

  const workerResult = await loadPreparedUsdStageOpenDataFromWorker(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    async () => {
      workerLoadCount += 1;
      return {
        stageSourcePath: '/robots/go2/usd/go2.usd',
        criticalDependencyPaths: [],
        preloadFiles: [
          {
            path: '/robots/go2/usd/go2.usd',
            blob: new Blob(['worker-root']),
            error: null,
          },
        ],
      };
    },
  );

  const inlineResult = await loadPreparedUsdStageOpenDataInline(
    demoSourceFile,
    demoAvailableFiles,
    demoAssets,
    async () => {
      inlineLoadCount += 1;
      return {
        stageSourcePath: '/robots/go2/usd/go2.usd',
        criticalDependencyPaths: [],
        preloadFiles: [
          {
            path: '/robots/go2/usd/go2.usd',
            blob: new Blob(['inline-root']),
            error: null,
          },
        ],
      };
    },
  );

  assert.equal(workerLoadCount, 1);
  assert.equal(inlineLoadCount, 1);
  assert.notStrictEqual(inlineResult, workerResult);
});

test('buildPreparedUsdStageOpenCacheKey ignores unrelated sibling USD files and assets', () => {
  const sourceFile = {
    name: 'robots/go2/usd/go2.usd',
    content: '#usda 1.0\n(\n  subLayers = [@./configuration/go2_description_base.usd@]\n)\n',
    blobUrl: undefined,
  };

  const narrowKey = buildPreparedUsdStageOpenCacheKey(
    sourceFile,
    [
      {
        name: 'robots/go2/usd/configuration/go2_description_base.usd',
        content: '#usda 1.0',
        blobUrl: undefined,
        format: 'usd',
      },
    ],
    {},
  );

  const wideKey = buildPreparedUsdStageOpenCacheKey(
    sourceFile,
    [
      {
        name: 'robots/go2/usd/configuration/go2_description_base.usd',
        content: '#usda 1.0',
        blobUrl: undefined,
        format: 'usd',
      },
      {
        name: 'robots/go2/usd/go2_alt.usd',
        content: '#usda 1.0',
        blobUrl: undefined,
        format: 'usd',
      },
      {
        name: 'robots/alien/usd/alien.usd',
        content: '#usda 1.0',
        blobUrl: undefined,
        format: 'usd',
      },
    ],
    {
      'robots/go2/textures/body.png': 'blob:go2-texture',
      'robots/alien/textures/body.png': 'blob:alien-texture',
    },
  );

  assert.equal(wideKey, narrowKey);
});

test('loadPreparedUsdStageOpenDataFromWorker rejects when worker preparation fails', async () => {
  let prepareCallCount = 0;

  await assert.rejects(
    loadPreparedUsdStageOpenDataFromWorker(
      demoSourceFile,
      demoAvailableFiles,
      demoAssets,
      async () => {
        prepareCallCount += 1;
        throw new Error('worker exploded');
      },
    ),
    /worker exploded/i,
  );

  assert.equal(prepareCallCount, 1);
});

test('loadPreparedUsdStageOpenDataFromWorker rejects incomplete worker payloads instead of allowing a main-thread repair path', async () => {
  let prepareCallCount = 0;

  await assert.rejects(
    loadPreparedUsdStageOpenDataFromWorker(
      demoSourceFile,
      demoAvailableFiles,
      demoAssets,
      async () => {
        prepareCallCount += 1;
        return {
          stageSourcePath: '/robots/go2/usd/go2.usd',
          criticalDependencyPaths: [],
          preloadFiles: [
            {
              path: '/robots/go2/usd/go2.usd',
              blob: null,
              error: 'missing-root',
            },
          ],
        };
      },
    ),
    /returned no root stage payload/i,
  );

  assert.equal(prepareCallCount, 1);
});

test('buildPreparedUsdStageOpenCacheKey samples blob-backed large USDA text instead of depending on the full content string', () => {
  const largeA = 'A'.repeat(1024 * 1024 + 64);
  const largeB = 'B'.repeat(1024 * 1024 + 64);

  const keyA = buildPreparedUsdStageOpenCacheKey(
    {
      name: 'robots/go2/usd/configuration/go2_description_base.usda',
      content: largeA,
      blobUrl: 'blob:go2-base',
    },
    [],
    {},
  );
  const keyB = buildPreparedUsdStageOpenCacheKey(
    {
      name: 'robots/go2/usd/configuration/go2_description_base.usda',
      content: largeB,
      blobUrl: 'blob:go2-base',
    },
    [],
    {},
  );
  const keyWithDifferentBlobUrl = buildPreparedUsdStageOpenCacheKey(
    {
      name: 'robots/go2/usd/configuration/go2_description_base.usda',
      content: largeA,
      blobUrl: 'blob:go2-base-2',
    },
    [],
    {},
  );

  assert.notEqual(keyA, keyB);
  assert.notEqual(keyA, keyWithDifferentBlobUrl);
});
