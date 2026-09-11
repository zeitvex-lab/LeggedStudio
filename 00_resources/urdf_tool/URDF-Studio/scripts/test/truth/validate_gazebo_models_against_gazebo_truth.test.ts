import assert from 'node:assert/strict';
import test from 'node:test';

import { JointType, GeometryType, type RobotData } from '@/types';

import {
  compareGazeboTruthToRobotData,
  type GazeboTruthModel,
} from './validate_gazebo_models_against_gazebo_truth.ts';

const identityPose = {
  xyz: { x: 0, y: 0, z: 0 },
  rpy: { r: 0, p: 0, y: 0 },
};

test('compareGazeboTruthToRobotData reports missing structure and joint parameter drift', () => {
  const truth: GazeboTruthModel = {
    modelName: 'truth_demo',
    links: {
      base: {
        name: 'base',
        worldPose: identityPose,
        visuals: [{ type: 'box', localPose: identityPose }],
        collisions: [{ type: 'box', localPose: identityPose }],
      },
      tool: {
        name: 'tool',
        worldPose: identityPose,
        visuals: [],
        collisions: [],
      },
      pose_link: {
        name: 'pose_link',
        worldPose: identityPose,
        visuals: [],
        collisions: [{ type: 'box', localPose: identityPose }],
      },
    },
    joints: {
      hinge: {
        name: 'hinge',
        type: JointType.REVOLUTE,
        parent: 'base',
        child: 'tool',
        origin: identityPose,
        axis: { x: 0, y: 0, z: 1 },
        limit: { lower: -1, upper: 1, effort: 4, velocity: 5 },
        dynamics: { damping: 0.2, friction: 0.3 },
      },
    },
  };

  const robot: RobotData = {
    name: 'truth_demo',
    rootLinkId: 'base',
    selection: { type: 'link', id: 'base' },
    links: {
      base: {
        id: 'base',
        name: 'base',
        visible: true,
        visual: {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 1, z: 1 },
          origin: identityPose,
        },
        visualBodies: [],
        collision: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          origin: identityPose,
        },
        collisionBodies: [],
        inertial: { mass: 0, origin: identityPose },
      },
      pose_link: {
        id: 'pose_link',
        name: 'pose_link',
        visible: true,
        visual: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          origin: identityPose,
        },
        visualBodies: [],
        collision: {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 1 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collisionBodies: [],
        inertial: { mass: 0, origin: identityPose },
      },
    },
    joints: {
      hinge: {
        id: 'hinge',
        name: 'hinge',
        type: JointType.REVOLUTE,
        parentLinkId: 'base',
        childLinkId: 'tool_imported',
        origin: identityPose,
        axis: { x: 1, y: 0, z: 0 },
        limit: { lower: -2, upper: 2, effort: 4, velocity: 6 },
        dynamics: { damping: 0, friction: 0.3 },
        hardware: {
          armature: 0,
          brand: '',
          motorType: 'None',
          motorId: '',
          motorDirection: 1,
        },
      },
    },
  };

  const report = compareGazeboTruthToRobotData(truth, robot);

  assert.deepEqual(report.missingLinks, ['tool']);
  assert.equal(report.missingJoints.length, 0);
  assert.equal(report.jointAxisMismatches[0]?.name, 'hinge');
  assert.equal(report.jointLimitMismatches[0]?.field, 'lower');
  assert.equal(report.jointDynamicsMismatches[0]?.field, 'damping');
  assert.deepEqual(report.jointEndpointMismatches, [
    {
      name: 'hinge',
      expectedParent: 'base',
      expectedChild: 'tool',
      actualParent: 'base',
      actualChild: 'tool_imported',
    },
  ]);
  assert.deepEqual(report.collisionCountMismatches, [
    { name: 'base', expected: 1, actual: 0 },
  ]);
  assert.equal(report.collisionPoseMismatches[0]?.name, 'pose_link#0');
});
