import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, type RobotState } from '@/types';

import {
  assertUsdExportWorkerSupport,
  getUsdExportWorkerUnsupportedMeshPaths,
  isUsdExportWorkerSupportedMeshPath,
} from './usdExportWorkerSupport.ts';

function createRobot(meshPaths: string[]): RobotState {
  return {
    name: 'worker_support_bot',
    rootLinkId: 'base_link',
    selection: { type: null, id: null },
    links: meshPaths.reduce<RobotState['links']>((links, meshPath, index) => {
      const linkId = `link_${index}`;
      links[linkId] = {
        id: linkId,
        name: linkId,
        visible: true,
        visual: {
          type: GeometryType.MESH,
          meshPath,
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#ffffff',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#cccccc',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: {
          mass: 1,
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
        },
      };
      return links;
    }, {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visible: true,
        visual: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#ffffff',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#cccccc',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: {
          mass: 1,
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
        },
      },
    }),
    joints: {},
  };
}

test('usdExport worker support accepts mesh formats with implemented worker loaders', () => {
  assert.equal(isUsdExportWorkerSupportedMeshPath('meshes/base_link.obj'), true);
  assert.equal(isUsdExportWorkerSupportedMeshPath('meshes/base_link.STL'), true);
  assert.equal(isUsdExportWorkerSupportedMeshPath('meshes/base_link.msh'), true);
  assert.equal(isUsdExportWorkerSupportedMeshPath('meshes/base_link.dae'), true);
  assert.equal(isUsdExportWorkerSupportedMeshPath('meshes/base_link.glb'), true);
  assert.equal(isUsdExportWorkerSupportedMeshPath('meshes/base_link.gltf'), true);
  assert.equal(isUsdExportWorkerSupportedMeshPath('package://robot/meshes/base.obj?cache=1'), true);
});

test('usdExport worker support still rejects mesh formats without a USD worker loader path', () => {
  const unsupported = getUsdExportWorkerUnsupportedMeshPaths(createRobot([
    'meshes/body.fbx',
    'meshes/body.ply',
    'meshes/body.obj',
  ]));

  assert.deepEqual(unsupported, [
    'meshes/body.fbx',
    'meshes/body.ply',
  ]);
});

test('usdExport worker support throws a fail-fast error for unsupported mesh formats', () => {
  assert.throws(
    () => assertUsdExportWorkerSupport(createRobot([
      'package://demo/meshes/base.fbx',
      'package://demo/meshes/arm.obj',
    ])),
    /USD export worker currently supports OBJ\/STL\/MSH\/DAE\/GLTF\/GLB mesh assets only/i,
  );
});
