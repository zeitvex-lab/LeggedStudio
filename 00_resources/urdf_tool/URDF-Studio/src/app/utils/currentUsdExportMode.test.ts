import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveCurrentUsdExportMode } from './currentUsdExportMode.ts';

test('keeps USD export unavailable while hydration is pending even if cached data exists', () => {
  assert.equal(
    resolveCurrentUsdExportMode({
      isHydrating: true,
      hasPreparedExportCache: true,
      hasSceneSnapshot: true,
    }),
    'unavailable',
  );
});

test('falls back to cached bundle export once USD hydration is finished', () => {
  assert.equal(
    resolveCurrentUsdExportMode({
      isHydrating: false,
      hasPreparedExportCache: true,
      hasSceneSnapshot: false,
    }),
    'bundle',
  );
});

test('reports USD export unavailable when cached export data does not exist', () => {
  assert.equal(
    resolveCurrentUsdExportMode({
      isHydrating: true,
      hasPreparedExportCache: false,
      hasSceneSnapshot: false,
    }),
    'unavailable',
  );
});
