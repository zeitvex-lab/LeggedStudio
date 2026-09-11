import test from 'node:test';
import assert from 'node:assert/strict';

import {
  resolveUsdStageHydrationSelection,
  shouldDeferUsdStageHydrationSelectionCleanup,
  shouldApplyUsdStageHydration,
} from './usdStageHydration.ts';

test('applies USD stage hydration only for the pending selected file', () => {
  assert.equal(shouldApplyUsdStageHydration({
    pendingFileName: 'robots/demo/scene.usd',
    selectedFileName: 'robots/demo/scene.usd',
    stageSourcePath: '/robots/demo/scene.usd',
  }), true);
});

test('skips USD stage hydration when the resolved stage no longer matches the selected file', () => {
  assert.equal(shouldApplyUsdStageHydration({
    pendingFileName: 'robots/demo/scene.usd',
    selectedFileName: 'robots/demo/other.usd',
    stageSourcePath: '/robots/demo/scene.usd',
  }), false);
});

test('skips USD stage hydration after the initial pending file marker is cleared', () => {
  assert.equal(shouldApplyUsdStageHydration({
    pendingFileName: null,
    selectedFileName: 'robots/demo/scene.usd',
    stageSourcePath: '/robots/demo/scene.usd',
  }), false);
});

test('defers selection cleanup while the active USD document is still loading', () => {
  assert.equal(
    shouldDeferUsdStageHydrationSelectionCleanup({
      documentLoadFileName: 'robots/demo/scene.usd',
      documentLoadFormat: 'usd',
      documentLoadStatus: 'loading',
      selectedFileFormat: 'usd',
      selectedFileName: 'robots/demo/scene.usd',
    }),
    true,
  );
});

test('does not defer selection cleanup after USD hydration reaches ready', () => {
  assert.equal(
    shouldDeferUsdStageHydrationSelectionCleanup({
      documentLoadFileName: 'robots/demo/scene.usd',
      documentLoadFormat: 'usd',
      documentLoadStatus: 'ready',
      selectedFileFormat: 'usd',
      selectedFileName: 'robots/demo/scene.usd',
    }),
    false,
  );
});

test('preserves a valid link selection made while a USD stage is hydrating', () => {
  assert.deepEqual(
    resolveUsdStageHydrationSelection({
      currentSelection: {
        type: 'link',
        id: 'pelvis',
        subType: 'visual',
        objectIndex: 0,
      },
      robotData: {
        links: {
          pelvis: { name: 'pelvis' },
        },
        joints: {},
      },
    }),
    {
      type: 'link',
      id: 'pelvis',
      subType: 'visual',
      objectIndex: 0,
    },
  );
});

test('clears stale USD hydration selections that do not exist in the committed robot', () => {
  assert.deepEqual(
    resolveUsdStageHydrationSelection({
      currentSelection: {
        type: 'link',
        id: 'old_base',
      },
      robotData: {
        links: {
          pelvis: { name: 'pelvis' },
        },
        joints: {},
      },
    }),
    { type: null, id: null },
  );
});
