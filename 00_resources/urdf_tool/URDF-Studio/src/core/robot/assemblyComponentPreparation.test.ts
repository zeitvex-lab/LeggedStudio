import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_JOINT, DEFAULT_LINK, GeometryType, JointType, type RobotData } from '@/types';

import {
  buildAssemblyComponentIdentity,
  prepareAssemblyRobotData,
  resolveAssemblyComponentBaseName,
} from './assemblyComponentPreparation.ts';

function createSourceRobot(): RobotData {
  return {
    name: 'authored_robot',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        ...structuredClone(DEFAULT_LINK),
        id: 'base_link',
        name: 'authored_base',
      },
      finger_link: {
        ...structuredClone(DEFAULT_LINK),
        id: 'finger_link',
        name: 'authored_finger',
      },
    },
    joints: {
      driver_joint: {
        ...structuredClone(DEFAULT_JOINT),
        id: 'driver_joint',
        name: 'authored_driver',
        type: JointType.PRISMATIC,
        parentLinkId: 'base_link',
        childLinkId: 'finger_link',
      },
      mimic_joint: {
        ...structuredClone(DEFAULT_JOINT),
        id: 'mimic_joint',
        name: 'authored_mimic',
        parentLinkId: 'base_link',
        childLinkId: 'finger_link',
        mimic: { joint: 'driver_joint', multiplier: -1 },
      },
    },
    materials: { base_link: { color: '#ff6600' } },
    closedLoopConstraints: [
      {
        id: 'finger_loop',
        type: 'connect',
        linkAId: 'base_link',
        linkBId: 'finger_link',
        anchorWorld: { x: 0, y: 0, z: 0 },
        anchorLocalA: { x: 0, y: 0, z: 0 },
        anchorLocalB: { x: 0, y: 0, z: 0 },
      },
    ],
    inspectionContext: {
      sourceFormat: 'mjcf',
      mjcf: {
        siteCount: 0,
        tendonCount: 1,
        tendonActuatorCount: 0,
        bodiesWithSites: [],
        tendons: [
          {
            name: 'finger_tendon',
            type: 'fixed',
            attachmentRefs: ['driver_joint'],
            attachments: [{ type: 'joint', ref: 'driver_joint' }],
            actuatorNames: [],
          },
        ],
      },
    },
  };
}

test('buildAssemblyComponentIdentity creates a stable unique component id and display name', () => {
  const identity = buildAssemblyComponentIdentity({
    fileName: 'robots/demo/my robot.urdf',
    existingComponentIds: new Set(['comp_my_robot']),
    existingComponentNames: new Set(['my_robot']),
  });

  assert.equal(identity.displayName, 'my_robot_1');
  assert.equal(identity.componentId, 'comp_my_robot_1');
});

test('buildAssemblyComponentIdentity uses model package names for generic model files', () => {
  const identity = buildAssemblyComponentIdentity({
    fileName: 'test/gazebo_models/arm_part/model.sdf',
    existingComponentIds: new Set(['comp_arm_part']),
    existingComponentNames: new Set(['arm_part']),
  });

  assert.equal(identity.displayName, 'arm_part_1');
  assert.equal(identity.componentId, 'comp_arm_part_1');
});

test('resolveAssemblyComponentBaseName prefers the authored source model name', () => {
  const name = resolveAssemblyComponentBaseName({
    name: 'test/gazebo_models/arm_part/model.sdf',
    format: 'sdf',
    content: `<?xml version="1.0"?>
<sdf version="1.7">
  <model name="arm_part">
    <link name="link" />
  </model>
</sdf>`,
  });

  assert.equal(name, 'arm_part');
});

test('prepareAssemblyRobotData normalizes materials while deep-cloning source-local entities', () => {
  const source = createSourceRobot();
  const prepared = prepareAssemblyRobotData(source, {
    sourceFormat: 'mjcf',
  });

  const expected = structuredClone(source);
  expected.links.base_link!.visual.color = '#ff6600';
  assert.deepEqual(prepared, expected);
  assert.notEqual(prepared, source);
  assert.notEqual(prepared.links.base_link, source.links.base_link);
  assert.equal(source.links.base_link?.visual.color, DEFAULT_LINK.visual.color);
  assert.equal(prepared.rootLinkId, 'base_link');
  assert.equal(prepared.links.base_link?.name, 'authored_base');
  assert.equal(prepared.joints.mimic_joint?.mimic?.joint, 'driver_joint');
  assert.equal(prepared.materials?.base_link?.color, '#ff6600');
  assert.equal(prepared.closedLoopConstraints?.[0]?.linkBId, 'finger_link');
  assert.equal(prepared.inspectionContext?.mjcf?.tendons[0]?.attachments[0]?.ref, 'driver_joint');
  assert.equal(prepared.links.component_with_underscores_base_link, undefined);
});

test('prepareAssemblyRobotData rewrites USD mesh paths without changing source-local ids', () => {
  const source = createSourceRobot();
  source.links.base_link.visual = {
    ...structuredClone(DEFAULT_LINK.visual),
    type: GeometryType.MESH,
    meshPath: 'base_link_visual_0.obj',
  };

  const prepared = prepareAssemblyRobotData(source, {
    sourceFilePath: 'robots/go2/usd/go2.usd',
    sourceFormat: 'usd',
  });

  assert.equal(prepared.rootLinkId, 'base_link');
  assert.equal(prepared.links.base_link?.visual.meshPath, 'robots/go2/usd/base_link_visual_0.obj');
  assert.equal(source.links.base_link?.visual.meshPath, 'base_link_visual_0.obj');
});

test('preparing the same source twice produces isolated source-local component robots', () => {
  const source = createSourceRobot();
  const first = prepareAssemblyRobotData(source, { sourceFormat: 'urdf' });
  const second = prepareAssemblyRobotData(source, { sourceFormat: 'urdf' });

  first.links.base_link!.name = 'first instance only';
  first.joints.driver_joint!.angle = 0.75;

  assert.equal(second.links.base_link?.name, 'authored_base');
  assert.equal(second.joints.driver_joint?.angle, undefined);
  assert.equal(source.links.base_link?.name, 'authored_base');
});
