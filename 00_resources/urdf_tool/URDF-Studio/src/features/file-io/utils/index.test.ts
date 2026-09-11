import test from 'node:test';
import assert from 'node:assert/strict';

import type {
  ExportRobotToUsdOptions,
  ExportRobotToUsdProgress,
} from './index.ts';

type UtilsBarrelTypeSmoke = [
  ExportRobotToUsdOptions,
  ExportRobotToUsdProgress,
];

void (0 as unknown as UtilsBarrelTypeSmoke);

test('file-io utils barrel exposes key runtime helpers', async () => {
  const moduleUnderTest = await import('./index.ts');

  assert.equal(typeof moduleUnderTest.createImportPathCollisionMap, 'function');
  assert.equal(typeof moduleUnderTest.remapImportedPath, 'function');
  assert.equal(typeof moduleUnderTest.exportRobotToUsd, 'function');
  assert.equal(typeof moduleUnderTest.exportRobotToUsdWithWorker, 'function');
  assert.equal(typeof moduleUnderTest.getUsdExportWorkerUnsupportedMeshPaths, 'function');
});
