import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_LINK, JointType, type AssemblyState, type UrdfJoint } from '@/types';

import { createAssemblyPersistenceSnapshot } from './semanticSnapshot.ts';

function createJoint(id: string, name: string, parentLinkId: string, childLinkId: string): UrdfJoint {
  return {
    id,
    name,
    type: JointType.FIXED,
    parentLinkId,
    childLinkId,
    origin: {
      xyz: { x: 0, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
    axis: { x: 0, y: 0, z: 1 },
    dynamics: { damping: 0, friction: 0 },
    hardware: {
      armature: 0,
      motorType: 'None',
      motorId: '',
      motorDirection: 1,
    },
  };
}

function createAssemblyState(): AssemblyState {
  return {
    name: 'demo_assembly',
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    components: {
      comp_demo: {
        id: 'comp_demo',
        name: 'demo',
        sourceFile: 'robots/demo.urdf',
        visible: true,
        transform: {
          position: { x: 0, y: 0, z: 0 },
          rotation: { r: 0, p: 0, y: 0 },
        },
        robot: {
          name: 'demo_robot',
          rootLinkId: 'comp_demo_base_link',
          links: {
            comp_demo_base_link: {
              ...DEFAULT_LINK,
              id: 'comp_demo_base_link',
              name: 'demo_base_link',
            },
          },
          joints: {},
        },
      },
    },
    bridges: {
      bridge_demo: {
        id: 'bridge_demo',
        name: 'bridge_demo',
        parentComponentId: 'comp_demo',
        parentLinkId: 'comp_demo_base_link',
        childComponentId: 'comp_demo',
        childLinkId: 'comp_demo_base_link',
        joint: createJoint(
          'bridge_demo',
          'bridge_demo_joint',
          'comp_demo_base_link',
          'comp_demo_base_link',
        ),
      },
    },
  };
}

test('createAssemblyPersistenceSnapshot ignores component visibility and transient bridge motion', () => {
  const baseline = createAssemblyState();
  const hidden = createAssemblyState();

  hidden.components.comp_demo.visible = false;
  hidden.components.comp_demo.robot.links.comp_demo_base_link.visible = false;
  hidden.bridges.bridge_demo.joint.angle = 0.6;

  assert.equal(
    createAssemblyPersistenceSnapshot(baseline),
    createAssemblyPersistenceSnapshot(hidden),
  );
});

test('createAssemblyPersistenceSnapshot detects structural assembly edits', () => {
  const baseline = createAssemblyState();
  const edited = createAssemblyState();

  edited.bridges.bridge_demo.joint.origin.xyz.x = 0.25;

  assert.notEqual(
    createAssemblyPersistenceSnapshot(baseline),
    createAssemblyPersistenceSnapshot(edited),
  );
});
