import test from 'node:test';
import assert from 'node:assert/strict';

import type { ExportRobotToUsdOptions, ExportRobotToUsdProgress } from './index.ts';

type FeatureBarrelTypeSmoke = [ExportRobotToUsdOptions, ExportRobotToUsdProgress];

void (0 as unknown as FeatureBarrelTypeSmoke);

test('file-io feature barrel exposes usd export entrypoint', async () => {
  const moduleUnderTest = await import('./index.ts');

  assert.equal(typeof moduleUnderTest.exportRobotToUsd, 'function');
  assert.equal(typeof moduleUnderTest.exportRobotToUsdWithWorker, 'function');
  assert.equal(typeof moduleUnderTest.getUsdExportWorkerUnsupportedMeshPaths, 'function');
  assert.equal('serializeUsdExportResultForWorker' in moduleUnderTest, false);
});
