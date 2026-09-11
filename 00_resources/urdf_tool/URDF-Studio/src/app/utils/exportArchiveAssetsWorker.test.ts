import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_LINK, GeometryType, type RobotState } from '@/types';

import {
  collectPreparedExportArchiveAssetTransferables,
  prepareExportArchiveAssets,
  type PrepareExportArchiveAssetsResult,
} from './exportArchiveAssetsWorker.ts';

function createDataUrl(content: string, mimeType = 'text/plain'): string {
  return `data:${mimeType};base64,${Buffer.from(content).toString('base64')}`;
}

function decodeBuffer(buffer: ArrayBuffer): string {
  return new TextDecoder().decode(buffer);
}

function createAssetRobot(): RobotState {
  return {
    name: 'worker_asset_zip',
    rootLinkId: 'base_link',
    selection: { type: null, id: null },
    links: {
      base_link: {
        ...DEFAULT_LINK,
        id: 'base_link',
        name: 'base_link',
        visual: {
          ...DEFAULT_LINK.visual,
          type: GeometryType.MESH,
          meshPath: 'package://demo/meshes/base.stl',
          dimensions: { x: 1, y: 1, z: 1 },
        },
      },
    },
    joints: {},
    materials: {
      base_link: {
        texture: 'package://demo/textures/body/coat.png',
      },
    },
  };
}

test('prepareExportArchiveAssets prepares mesh and texture ArrayBuffers', async () => {
  const progressEvents: string[] = [];

  const result = await prepareExportArchiveAssets({
    robot: createAssetRobot(),
    assets: {
      'package://demo/meshes/base.stl': createDataUrl('solid base\nendsolid base', 'model/stl'),
      'package://demo/textures/body/coat.png': createDataUrl('png-texture', 'image/png'),
    },
    onProgress: ({ completed, currentFile }) => {
      progressEvents.push(`${completed}:${currentFile}`);
    },
  });

  assert.equal(result.failedAssets.length, 0);
  assert.equal(result.totalTasks, 2);
  assert.equal(result.completedTasks, 2);

  const meshFile = result.files.find((file) => file.assetType === 'mesh');
  const textureFile = result.files.find((file) => file.assetType === 'texture');

  assert.equal(meshFile?.folder, 'meshes');
  assert.equal(meshFile?.exportPath, 'base.stl');
  assert.match(decodeBuffer(meshFile!.bytes), /solid base/);

  assert.equal(textureFile?.folder, 'textures');
  assert.equal(textureFile?.exportPath, 'body/coat.png');
  assert.equal(decodeBuffer(textureFile!.bytes), 'png-texture');
  assert.equal(progressEvents[0], '0:');
  assert.ok(progressEvents.includes('2:body/coat.png') || progressEvents.includes('2:base.stl'));
});

test('prepareExportArchiveAssets uses inline blobs and skipMeshPaths before asset lookup', async () => {
  const result = await prepareExportArchiveAssets({
    robot: createAssetRobot(),
    assets: {},
    extraMeshFiles: new Map([
      ['package://demo/meshes/base.stl', new Blob(['inline-mesh'], { type: 'model/stl' })],
      [
        'package://demo/textures/body/coat.png',
        new Blob(['inline-texture'], { type: 'image/png' }),
      ],
    ]),
    skipMeshPaths: new Set(['package://demo/meshes/base.stl']),
  });

  assert.equal(result.failedAssets.length, 0);
  assert.equal(result.totalTasks, 1);
  assert.equal(result.files.length, 1);
  assert.equal(result.files[0]?.assetType, 'texture');
  assert.equal(decodeBuffer(result.files[0]!.bytes), 'inline-texture');
});

test('collectPreparedExportArchiveAssetTransferables exposes result buffers for transfer', () => {
  const bytes = new Uint8Array([1, 2, 3, 4]).buffer;
  const result: PrepareExportArchiveAssetsResult = {
    totalTasks: 1,
    completedTasks: 1,
    failedAssets: [],
    files: [
      {
        assetType: 'mesh',
        folder: 'meshes',
        sourcePath: 'meshes/base.stl',
        exportPath: 'base.stl',
        bytes,
      },
    ],
  };

  const transferables = collectPreparedExportArchiveAssetTransferables(result);
  assert.deepEqual(transferables, [bytes]);

  const cloned = structuredClone(result, { transfer: transferables });
  assert.equal(bytes.byteLength, 0);
  assert.deepEqual(Array.from(new Uint8Array(cloned.files[0]!.bytes)), [1, 2, 3, 4]);
});
