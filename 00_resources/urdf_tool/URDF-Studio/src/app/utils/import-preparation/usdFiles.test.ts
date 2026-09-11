import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createImportedUsdFile,
  createImportedUsdFileFromLooseFile,
  isUsdFamilyPath,
} from './usdFiles.ts';

test('isUsdFamilyPath recognizes usd-family extensions only', () => {
  assert.equal(isUsdFamilyPath('robot/demo.usd'), true);
  assert.equal(isUsdFamilyPath('robot/demo.usda'), true);
  assert.equal(isUsdFamilyPath('robot/demo.usdc'), true);
  assert.equal(isUsdFamilyPath('robot/demo.usdz'), true);
  assert.equal(isUsdFamilyPath('robot/demo.txt'), false);
});

test('createImportedUsdFile keeps binary usd blob-backed', () => {
  const binaryBytes = new Uint8Array([80, 88, 82, 45, 85, 83, 68, 67, 1, 2, 3, 4]);

  assert.deepEqual(createImportedUsdFile('robot/demo.usd', binaryBytes), {
    name: 'robot/demo.usd',
    content: '',
    format: 'usd',
  });
});

test('createImportedUsdFile eagerly decodes text usd content', () => {
  const textBytes = new TextEncoder().encode('#usda 1.0\ndef Xform "demo" {}');

  assert.deepEqual(createImportedUsdFile('robot/demo.usd', textBytes), {
    name: 'robot/demo.usd',
    content: '#usda 1.0\ndef Xform "demo" {}',
    format: 'usd',
  });
});

test('createImportedUsdFileFromLooseFile respects loose file usd heuristics', async () => {
  const textUsdFile = new File(['#usda 1.0\ndef Xform "demo" {}'], 'demo.usda');
  const binaryUsdFile = new File([new Uint8Array([80, 88, 82, 45, 85, 83, 68, 67])], 'demo.usdc');
  const inferredTextUsdFile = new File(['#usda 1.0\ndef Xform "demo" {}'], 'demo.usd');

  assert.deepEqual(await createImportedUsdFileFromLooseFile('robot/demo.usda', textUsdFile), {
    name: 'robot/demo.usda',
    content: '#usda 1.0\ndef Xform "demo" {}',
    format: 'usd',
  });
  assert.deepEqual(await createImportedUsdFileFromLooseFile('robot/demo.usdc', binaryUsdFile), {
    name: 'robot/demo.usdc',
    content: '',
    format: 'usd',
  });
  assert.deepEqual(
    await createImportedUsdFileFromLooseFile('robot/demo.usd', inferredTextUsdFile),
    {
      name: 'robot/demo.usd',
      content: '#usda 1.0\ndef Xform "demo" {}',
      format: 'usd',
    },
  );
});
