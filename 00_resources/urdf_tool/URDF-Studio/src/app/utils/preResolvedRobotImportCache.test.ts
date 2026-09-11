import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, type RobotFile } from '@/types';
import {
  clearPreResolvedRobotImportCache,
  consumePreResolvedRobotImport,
  peekPreResolvedRobotImport,
  primePreResolvedRobotImports,
} from './preResolvedRobotImportCache';
import { buildPreResolvedImportContentSignature } from './preResolvedImportSignature.ts';

const demoFile: RobotFile = {
  name: 'robot/demo.xml',
  format: 'urdf',
  content: '<robot name="demo"><link name="base_link" /></robot>',
};

const demoResult = {
  status: 'ready' as const,
  format: 'urdf' as const,
  resolvedUrdfContent: demoFile.content,
  resolvedUrdfSourceFilePath: demoFile.name,
  robotData: {
    name: 'demo',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visible: true,
        visual: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#808080',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#ef4444',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: {
          mass: 1,
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          inertia: { ixx: 0.1, ixy: 0, ixz: 0, iyy: 0.1, iyz: 0, izz: 0.1 },
        },
      },
    },
    joints: {},
  },
};

test.afterEach(() => {
  clearPreResolvedRobotImportCache();
});

test('consumePreResolvedRobotImport returns a primed match once', () => {
  primePreResolvedRobotImports([{
    fileName: demoFile.name,
    format: demoFile.format,
    contentSignature: buildPreResolvedImportContentSignature(demoFile.content),
    result: demoResult,
  }]);

  const firstConsume = consumePreResolvedRobotImport(demoFile);
  const secondConsume = consumePreResolvedRobotImport(demoFile);

  assert.deepEqual(firstConsume, demoResult);
  assert.equal(secondConsume, null);
});

test('peekPreResolvedRobotImport keeps a primed match available for a later consume', () => {
  primePreResolvedRobotImports([{
    fileName: demoFile.name,
    format: demoFile.format,
    contentSignature: buildPreResolvedImportContentSignature(demoFile.content),
    result: demoResult,
  }]);

  const peekResult = peekPreResolvedRobotImport(demoFile);
  const consumeResult = consumePreResolvedRobotImport(demoFile);
  const secondConsume = consumePreResolvedRobotImport(demoFile);

  assert.deepEqual(peekResult, demoResult);
  assert.deepEqual(consumeResult, demoResult);
  assert.equal(secondConsume, null);
});

test('consumePreResolvedRobotImport ignores stale content mismatches', () => {
  primePreResolvedRobotImports([{
    fileName: demoFile.name,
    format: demoFile.format,
    contentSignature: buildPreResolvedImportContentSignature(demoFile.content),
    result: demoResult,
  }]);

  const consumeResult = consumePreResolvedRobotImport({
    ...demoFile,
    content: '<robot name="changed"><link name="base_link" /></robot>',
  });

  assert.equal(consumeResult, null);
});
