import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldBypassUsdWorkerPipeline } from './usdWorkerBypass';

test('keeps every USD bundle on the same worker preparation path', () => {
  assert.equal(shouldBypassUsdWorkerPipeline('/unitree_model/B2/usd/b2.usd'), false);
  assert.equal(
    shouldBypassUsdWorkerPipeline('/unitree_model/B2/usd/b2.viewer_roundtrip.usd'),
    false,
  );
  assert.equal(shouldBypassUsdWorkerPipeline('/unitree_model/b2w/usd/b2w.usd?cache=1'), false);
  assert.equal(shouldBypassUsdWorkerPipeline('b2.usd'), false);
  assert.equal(shouldBypassUsdWorkerPipeline('b2.viewer_roundtrip.usd'), false);
  assert.equal(shouldBypassUsdWorkerPipeline('B2W.USD'), false);
  assert.equal(shouldBypassUsdWorkerPipeline('/unitree_model/Go2/usd/go2.usd'), false);
  assert.equal(shouldBypassUsdWorkerPipeline('/robots/custom/usd/demo.usd'), false);
  assert.equal(shouldBypassUsdWorkerPipeline(null), false);
});
