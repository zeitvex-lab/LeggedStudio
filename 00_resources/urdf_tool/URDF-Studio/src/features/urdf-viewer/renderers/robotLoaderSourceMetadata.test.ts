import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, JointType, type RobotState, type UrdfJoint, type UrdfLink } from '@/types';

import { resolveRobotLoaderSourceMetadata } from './robotLoaderSourceMetadata';

const TEST_LINKS: Record<string, UrdfLink> = {
  base_link: {
    id: 'base_link',
    name: 'base_link',
    visual: {
      type: GeometryType.MESH,
      meshPath: 'package://demo_description/meshes/base.dae',
      dimensions: { x: 2, y: 2, z: 2 },
      color: '#ffffff',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 1.57 } },
    },
    collision: {
      type: GeometryType.MESH,
      meshPath: 'package://demo_description/meshes/base_collision.stl',
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#ffffff',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
  },
};

const TEST_JOINTS: Record<string, UrdfJoint> = {
  shoulder_joint: {
    id: 'shoulder_joint',
    name: 'shoulder_joint',
    type: JointType.REVOLUTE,
    parentLinkId: 'world',
    childLinkId: 'base_link',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    axis: { x: 0, y: 0, z: 1 },
    limit: { lower: -1, upper: 1, effort: 10, velocity: 5 },
    dynamics: { damping: 0, friction: 0 },
    hardware: { armature: 0, motorType: '', motorId: '', motorDirection: 1 },
  },
};

function createParsedRobot(): RobotState {
  return {
    name: 'demo',
    links: TEST_LINKS,
    joints: TEST_JOINTS,
    rootLinkId: 'base_link',
    selection: { type: null, id: null },
  };
}

test('resolveRobotLoaderSourceMetadata reuses pre-parsed links and joints without reparsing', () => {
  let parseCalls = 0;

  const metadata = resolveRobotLoaderSourceMetadata({
    urdfContent: '<robot name="demo" />',
    robotLinks: TEST_LINKS,
    robotJoints: TEST_JOINTS,
    parseRobot: () => {
      parseCalls += 1;
      return createParsedRobot();
    },
  });

  assert.equal(parseCalls, 0);
  assert.equal(metadata.robotLinks, TEST_LINKS);
  assert.equal(metadata.robotJoints, TEST_JOINTS);
  assert.deepEqual(Array.from(metadata.explicitlyScaledMeshPaths), ['package://demo_description/meshes/base.dae']);
  assert.equal(
    metadata.colladaRootNormalizationHints?.exactMeshPaths.has('demo_description/meshes/base.dae'),
    true,
  );
});

test('resolveRobotLoaderSourceMetadata falls back to parsing when runtime metadata is missing', () => {
  let parseCalls = 0;

  const metadata = resolveRobotLoaderSourceMetadata({
    urdfContent: '<robot name="demo" />',
    robotLinks: TEST_LINKS,
    parseRobot: () => {
      parseCalls += 1;
      return createParsedRobot();
    },
  });

  assert.equal(parseCalls, 1);
  assert.equal(metadata.robotLinks, TEST_LINKS);
  assert.equal(metadata.robotJoints, TEST_JOINTS);
  assert.deepEqual(Array.from(metadata.explicitlyScaledMeshPaths), ['package://demo_description/meshes/base.dae']);
});
