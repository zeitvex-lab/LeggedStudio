import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  JointType,
  type AssemblyState,
  type RobotData,
} from '@/types';
import { createSingleComponentWorkspace } from './canonicalWorkspace.ts';
import {
  createComponentSourceDraft,
  createSourceSemanticRobotHash,
  requireSourcePreservingComponentDraft,
  resolveSourcePreservingComponentDraft,
} from './componentSourceDraft.ts';

function robot(): RobotData {
  return {
    name: 'source_robot',
    rootLinkId: 'base',
    links: {
      base: {
        ...structuredClone(DEFAULT_LINK),
        id: 'base',
        name: 'base',
        inertial: {
          mass: 2,
          inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
        },
      },
      tip: { ...structuredClone(DEFAULT_LINK), id: 'tip', name: 'tip' },
    },
    joints: {
      hinge: {
        ...structuredClone(DEFAULT_JOINT),
        id: 'hinge',
        name: 'hinge',
        type: JointType.REVOLUTE,
        parentLinkId: 'base',
        childLinkId: 'tip',
      },
    },
    materials: { steel: { color: '#777777' } },
    inspectionContext: {
      sourceFormat: 'mjcf',
      mjcf: {
        siteCount: 0,
        tendonCount: 1,
        tendonActuatorCount: 0,
        bodiesWithSites: [],
        tendons: [{
          name: 'cable',
          type: 'fixed',
          width: 0.01,
          rgba: [1, 0, 0, 1],
          attachmentRefs: ['hinge'],
          attachments: [{ type: 'joint', ref: 'hinge', coef: 1 }],
          actuatorNames: [],
        }],
      },
    },
  };
}

function workspace(currentRobot = robot()): AssemblyState {
  return createSingleComponentWorkspace(currentRobot, {
    componentId: 'arm',
    sourceFile: 'library/arm.xml',
  });
}

test('source semantic hash ignores all transient joint motion fields', () => {
  const baseline = robot();
  const moved = structuredClone(baseline) as RobotData & {
    joints: RobotData['joints'] & { hinge: RobotData['joints'][string] & { jointValue?: number } };
  };
  moved.joints.hinge.angle = 0.7;
  moved.joints.hinge.jointValue = -0.3;
  moved.joints.hinge.quaternion = { x: 0, y: 0, z: 0.2, w: 0.98 };

  assert.equal(createSourceSemanticRobotHash(moved), createSourceSemanticRobotHash(baseline));
});

test('source semantic hash ignores presentation-only visibility', () => {
  const baseline = robot();
  const hidden = structuredClone(baseline);
  hidden.links.base.visible = false;
  hidden.links.base.visual.visible = false;
  hidden.links.base.collision.visible = false;

  assert.equal(createSourceSemanticRobotHash(hidden), createSourceSemanticRobotHash(baseline));
});

test('source semantic hash covers topology, material, inertial, collision, IK and tendon semantics', () => {
  const baseline = robot();
  const baselineHash = createSourceSemanticRobotHash(baseline);
  const edits: RobotData[] = [];

  const topology = structuredClone(baseline);
  topology.rootLinkId = 'tip';
  edits.push(topology);
  const material = structuredClone(baseline);
  material.materials!.steel.color = '#000000';
  edits.push(material);
  const inertial = structuredClone(baseline);
  inertial.links.base.inertial!.mass = 3;
  edits.push(inertial);
  const collision = structuredClone(baseline);
  collision.links.base.collision.dimensions.x = 4;
  edits.push(collision);
  const ik = structuredClone(baseline) as RobotData & { ik: { targetLinkId: string } };
  ik.ik = { targetLinkId: 'tip' };
  edits.push(ik);
  const tendon = structuredClone(baseline);
  tendon.inspectionContext!.mjcf!.tendons[0].width = 0.02;
  edits.push(tendon);

  edits.forEach((edited) => assert.notEqual(createSourceSemanticRobotHash(edited), baselineHash));
});

test('source-preserving resolver only returns a component-owned matching draft', () => {
  const currentWorkspace = workspace();
  const draft = createComponentSourceDraft({
    componentId: 'arm',
    format: 'mjcf',
    content: '<mujoco model="arm"/>',
    robot: currentWorkspace.components.arm.robot,
  });

  assert.deepEqual(resolveSourcePreservingComponentDraft({
    workspace: currentWorkspace,
    componentId: 'arm',
    drafts: { arm: draft },
  }), { status: 'matched', draft });

  const editedWorkspace = structuredClone(currentWorkspace);
  editedWorkspace.components.arm.robot.links.base.inertial!.mass = 8;
  assert.deepEqual(resolveSourcePreservingComponentDraft({
    workspace: editedWorkspace,
    componentId: 'arm',
    drafts: { arm: draft },
  }), { status: 'regenerate', reason: 'draft-stale' });
  assert.throws(() => requireSourcePreservingComponentDraft({
    workspace: editedWorkspace,
    componentId: 'arm',
    drafts: { arm: draft },
  }), /regenerate the source first/);
});
