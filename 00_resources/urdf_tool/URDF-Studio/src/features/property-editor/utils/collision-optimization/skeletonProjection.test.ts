import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_JOINT, DEFAULT_LINK, JointType, type RobotData } from '@/types';

import { buildCollisionOptimizationSkeletonProjection } from './skeletonProjection.ts';

function createProjectionRobot(): RobotData {
  return {
    name: 'projection-test',
    rootLinkId: 'base',
    links: {
      base: {
        ...DEFAULT_LINK,
        id: 'base',
        name: 'base',
      },
      shoulder: {
        ...DEFAULT_LINK,
        id: 'shoulder',
        name: 'shoulder',
      },
      wrist: {
        ...DEFAULT_LINK,
        id: 'wrist',
        name: 'wrist',
      },
      isolated: {
        ...DEFAULT_LINK,
        id: 'isolated',
        name: 'isolated',
      },
    },
    joints: {
      shoulder_joint: {
        ...DEFAULT_JOINT,
        id: 'shoulder_joint',
        name: 'shoulder_joint',
        type: JointType.FIXED,
        parentLinkId: 'base',
        childLinkId: 'shoulder',
        origin: {
          xyz: { x: 2, y: 0, z: 1 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
      wrist_joint: {
        ...DEFAULT_JOINT,
        id: 'wrist_joint',
        name: 'wrist_joint',
        type: JointType.FIXED,
        parentLinkId: 'shoulder',
        childLinkId: 'wrist',
        origin: {
          xyz: { x: 0, y: 3, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
    },
  };
}

test('skeleton projection picks the largest readable plane and preserves cluster membership', () => {
  const projection = buildCollisionOptimizationSkeletonProjection({
    kind: 'robot',
    robot: createProjectionRobot(),
  });

  assert.equal(projection.plane, 'xy');
  assert.deepEqual(projection.nodes.base.world, { x: 0, y: 0, z: 0 });
  assert.deepEqual(projection.nodes.shoulder.world, { x: 2, y: 0, z: 1 });
  assert.deepEqual(projection.nodes.wrist.world, { x: 2, y: 3, z: 1 });
  assert.deepEqual(projection.nodes.wrist.projected, { x: 2, y: -3 });
  assert.equal(projection.nodes.base.clusterId, projection.nodes.wrist.clusterId);
  assert.notEqual(projection.nodes.base.clusterId, projection.nodes.isolated.clusterId);
  assert.deepEqual(
    projection.edges.map((edge) => [edge.fromLinkId, edge.toLinkId]),
    [
      ['base', 'shoulder'],
      ['shoulder', 'wrist'],
    ],
  );
});

test('front skeleton projection uses the front-readable yz plane when lateral spread exists', () => {
  const projection = buildCollisionOptimizationSkeletonProjection(
    {
      kind: 'robot',
      robot: createProjectionRobot(),
    },
    { viewMode: 'front' },
  );

  assert.equal(projection.plane, 'yz');
  assert.deepEqual(projection.nodes.wrist.projected, { x: 3, y: -1 });
});
