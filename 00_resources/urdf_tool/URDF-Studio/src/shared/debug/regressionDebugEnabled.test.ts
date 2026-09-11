import test from 'node:test';
import assert from 'node:assert/strict';

import {
  clearRegressionDebugGlobals,
  isRegressionDebugEnabled,
} from './regressionDebugEnabled.ts';

test('isRegressionDebugEnabled requires the explicit regressionDebug query flag', () => {
  assert.equal(
    isRegressionDebugEnabled({ location: { search: '' } } as Window),
    false,
  );
  assert.equal(
    isRegressionDebugEnabled({ location: { search: '?regressionDebug=1' } } as Window),
    true,
  );
});

test('clearRegressionDebugGlobals removes regression window globals', () => {
  const targetWindow = {
    __URDF_STUDIO_DEBUG__: {},
    __URDF_STUDIO_MESH_LOAD_PERFORMANCE__: {},
    __URDF_STUDIO_MESH_LOAD_PERFORMANCE_HISTORY__: [],
    __usdStageLoadDebug: {},
    __usdStageLoadDebugHistory: [],
    __visualizerCollisionLoadDebug: {},
    __visualizerCollisionLoadDebugHistory: [],
  } as unknown as Window & Record<string, unknown>;

  clearRegressionDebugGlobals(targetWindow);

  assert.equal('__URDF_STUDIO_DEBUG__' in targetWindow, false);
  assert.equal('__URDF_STUDIO_MESH_LOAD_PERFORMANCE__' in targetWindow, false);
  assert.equal('__URDF_STUDIO_MESH_LOAD_PERFORMANCE_HISTORY__' in targetWindow, false);
  assert.equal('__usdStageLoadDebug' in targetWindow, false);
  assert.equal('__usdStageLoadDebugHistory' in targetWindow, false);
  assert.equal('__visualizerCollisionLoadDebug' in targetWindow, false);
  assert.equal('__visualizerCollisionLoadDebugHistory' in targetWindow, false);
});
