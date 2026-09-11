import test from 'node:test';
import assert from 'node:assert/strict';

test('urdf-viewer utils barrel exposes app-facing export helpers', async () => {
  const moduleUnderTest = await import('./index.ts');

  assert.equal(typeof moduleUnderTest.getUsdStageExportHandler, 'function');
  assert.equal(typeof moduleUnderTest.exportUsdStageSnapshot, 'function');
  assert.equal(typeof moduleUnderTest.buildUsdExportBundleFromPreparedCache, 'function');
  assert.equal(typeof moduleUnderTest.buildUsdExportBundleFromSnapshot, 'function');
  assert.equal(typeof moduleUnderTest.resolveUsdExportSceneSnapshot, 'function');
  assert.equal(typeof moduleUnderTest.createStableViewerResourceScope, 'function');
  assert.equal(typeof moduleUnderTest.ensureUsdWasmRuntime, 'function');
  assert.equal(typeof moduleUnderTest.prewarmUsdWasmRuntimeInBackground, 'function');
  assert.equal(typeof moduleUnderTest.prewarmUsdOffscreenViewerRuntimeInBackground, 'function');
  assert.equal(typeof moduleUnderTest.toVirtualUsdPath, 'function');
  assert.equal('createUsdOffscreenViewerWorkerClient' in moduleUnderTest, false);
  assert.equal('supportsUsdWorkerRenderer' in moduleUnderTest, false);
});
