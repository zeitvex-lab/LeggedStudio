import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, JointType, type RobotState } from '@/types';
import { buildInspectionRobotContext } from './buildInspectionRobotContext.ts';

test('buildInspectionRobotContext preserves joint engineering fields and MJCF inspection metadata', () => {
  const robot: RobotState = {
    name: 'inspection-fixture',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visual: {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 2, z: 3 },
          color: '#ffffff',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 2, z: 3 },
          color: '#000000',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: {
          mass: 2,
          inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0.1 }, rpy: { r: 0, p: 0, y: 0 } },
        },
      },
    },
    joints: {
      hip_joint: {
        id: 'hip_joint',
        name: 'hip_joint',
        type: JointType.REVOLUTE,
        parentLinkId: 'world',
        childLinkId: 'base_link',
        origin: { xyz: { x: 0, y: 0.2, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        axis: { x: 0, y: 1, z: 0 },
        limit: { lower: -1, upper: 1, effort: 12, velocity: 8 },
        dynamics: { damping: 0.1, friction: 0.2 },
        hardware: { armature: 0.03, motorType: 'servo', motorId: 'M1', motorDirection: 1 },
        referencePosition: 0.12,
      },
    },
    inspectionContext: {
      sourceFormat: 'mjcf',
      mjcf: {
        siteCount: 2,
        tendonCount: 1,
        tendonActuatorCount: 1,
        bodiesWithSites: [
          { bodyId: 'base_link', siteCount: 2, siteNames: ['tip_site', 'frame_site'] },
        ],
        tendons: [
          {
            name: 'finger_tendon',
            type: 'spatial',
            limited: true,
            range: [0, 1],
            attachmentRefs: ['tip_site', 'frame_site'],
            attachments: [
              { type: 'site', ref: 'tip_site' },
              { type: 'site', ref: 'frame_site' },
            ],
            actuatorNames: ['finger_motor'],
          },
        ],
      },
    },
    selection: { type: 'link', id: 'base_link' },
  };

  const context = buildInspectionRobotContext(robot);
  const [joint] = context.joints;

  assert.equal(joint?.name, 'hip_joint');
  assert.deepEqual(joint?.origin, { xyz: { x: 0, y: 0.2, z: 0 }, rpy: { r: 0, p: 0, y: 0 } });
  assert.deepEqual(joint?.limit, { lower: -1, upper: 1, effort: 12, velocity: 8 });
  assert.deepEqual(joint?.dynamics, { damping: 0.1, friction: 0.2 });
  assert.deepEqual(joint?.hardware, {
    armature: 0.03,
    motorType: 'servo',
    motorId: 'M1',
    motorDirection: 1,
  });
  assert.equal(joint?.referencePosition, 0.12);

  assert.deepEqual(context.inspectionContext, robot.inspectionContext);
});

test('buildInspectionRobotContext exposes friendly MJCF link and joint names in AI context', () => {
  const robot: RobotState = {
    name: 'inspection-fixture',
    rootLinkId: 'world_body_0',
    links: {
      world_body_0: {
        id: 'world_body_0',
        name: 'world_body_0',
        visual: {
          type: GeometryType.MESH,
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#ffffff',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          mjcfMesh: { name: 'bin' },
        },
        collision: {
          type: GeometryType.MESH,
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#000000',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          mjcfMesh: { name: 'bin' },
        },
      },
    },
    joints: {
      world_to_world_body_0: {
        id: 'world_to_world_body_0',
        name: 'world_to_world_body_0',
        type: JointType.FIXED,
        parentLinkId: 'world',
        childLinkId: 'world_body_0',
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        dynamics: { damping: 0, friction: 0 },
        hardware: { armature: 0, motorType: '', motorId: '', motorDirection: 1 },
      },
    },
    inspectionContext: {
      sourceFormat: 'mjcf',
      mjcf: {
        siteCount: 0,
        tendonCount: 0,
        tendonActuatorCount: 0,
        bodiesWithSites: [],
        tendons: [],
      },
    },
    selection: { type: 'link', id: 'world_body_0' },
  };

  const context = buildInspectionRobotContext(robot);

  assert.equal(context.links[0]?.name, 'Bin');
  assert.equal(context.joints[0]?.name, 'World to Bin');
});
