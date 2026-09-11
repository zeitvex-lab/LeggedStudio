import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
import * as THREE from 'three';
import { URDFJoint } from '@/core/parsers/urdf/loader';
import { parseMJCF } from '@/core/parsers/mjcf/mjcfParser.ts';
import { JointType, type InteractionSelection, type UrdfJoint } from '@/types';
import {
  applyOriginToRuntimeJoint,
  extractRuntimeJointOrigin,
  resolveOriginTransformClosedLoopPreview,
  resolveOriginTransformJointId,
  resolveOriginTransformTarget,
} from './originTransformControlsShared.ts';

function installDomGlobals(): void {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { contentType: 'text/html' });
  globalThis.window = dom.window as any;
  globalThis.document = dom.window.document as any;
  globalThis.DOMParser = dom.window.DOMParser as any;
  globalThis.XMLSerializer = dom.window.XMLSerializer as any;
  globalThis.Node = dom.window.Node as any;
  globalThis.Element = dom.window.Element as any;
  globalThis.Document = dom.window.Document as any;
}

function createRobotJointsFixture(): Record<string, UrdfJoint> {
  return {
    fixed_mount: {
      id: 'fixed_mount',
      name: 'fixed_mount',
      type: JointType.FIXED,
      parentLinkId: 'base_link',
      childLinkId: 'sensor_mount',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      dynamics: { damping: 0, friction: 0 },
      hardware: { armature: 0, motorType: '', motorId: '', motorDirection: 1 },
    },
    hip_joint: {
      id: 'hip_joint',
      name: 'hip_joint',
      type: JointType.REVOLUTE,
      parentLinkId: 'base_link',
      childLinkId: 'hip_link',
      origin: { xyz: { x: 0.1, y: 0, z: 0.2 }, rpy: { r: 0, p: 0, y: 0 } },
      axis: { x: 0, y: 0, z: 1 },
      limit: { lower: -Math.PI, upper: Math.PI, effort: 10, velocity: 10 },
      dynamics: { damping: 0, friction: 0 },
      hardware: { armature: 0, motorType: '', motorId: '', motorDirection: 1 },
    },
  };
}

test('resolveOriginTransformJointId maps a child link origin helper to its parent joint', () => {
  const selection: InteractionSelection = {
    type: 'link',
    id: 'hip_link',
    helperKind: 'origin-axes',
  };

  assert.equal(resolveOriginTransformJointId(selection, createRobotJointsFixture()), 'hip_joint');
});

test('resolveOriginTransformJointId leaves the root link origin helper without a joint mapping', () => {
  const selection: InteractionSelection = {
    type: 'link',
    id: 'base_link',
    helperKind: 'origin-axes',
  };

  assert.equal(resolveOriginTransformJointId(selection, createRobotJointsFixture()), null);
});

test('resolveOriginTransformTarget resolves runtime joints from source joint ids using the authored joint name', () => {
  const robot = new THREE.Group() as THREE.Group & {
    joints?: Record<string, URDFJoint>;
  };
  const runtimeJoint = new URDFJoint();
  runtimeJoint.name = 'hip_joint_runtime';
  runtimeJoint.jointType = 'revolute';
  robot.joints = {
    hip_joint_runtime: runtimeJoint,
  };

  const selection: InteractionSelection = {
    type: 'joint',
    id: 'hip_joint_source',
    helperKind: 'origin-axes',
  };

  const resolved = resolveOriginTransformTarget(robot, selection, {
    hip_joint_source: {
      ...createRobotJointsFixture().hip_joint,
      id: 'hip_joint_source',
      name: 'hip_joint_runtime',
    },
  });

  assert.ok(resolved);
  assert.equal(resolved?.jointId, 'hip_joint_source');
  assert.equal(resolved?.runtimeJointKey, 'hip_joint_runtime');
  assert.equal(resolved?.runtimeJoint, runtimeJoint);
});

test('resolveOriginTransformTarget does not remap root link origin helpers to child joints', () => {
  const robot = new THREE.Group() as THREE.Group & {
    joints?: Record<string, URDFJoint>;
  };
  const runtimeJoint = new URDFJoint();
  runtimeJoint.name = 'hip_joint_runtime';
  runtimeJoint.jointType = 'revolute';
  robot.joints = {
    hip_joint_runtime: runtimeJoint,
  };

  const selection: InteractionSelection = {
    type: 'link',
    id: 'base_link',
    helperKind: 'origin-axes',
  };

  const resolved = resolveOriginTransformTarget(robot, selection, {
    fixed_mount: createRobotJointsFixture().fixed_mount,
    hip_joint_source: {
      ...createRobotJointsFixture().hip_joint,
      id: 'hip_joint_source',
      name: 'hip_joint_runtime',
    },
  });

  assert.equal(resolved, null);
});

test('applyOriginToRuntimeJoint preserves the active joint value while replacing the authored origin', () => {
  const joint = new URDFJoint();
  joint.name = 'hip_joint';
  joint.jointType = 'revolute';
  joint.axis = new THREE.Vector3(0, 0, 1);
  joint.limit = { lower: -Math.PI, upper: Math.PI };
  joint.position.set(0, 0, 0.2);
  joint.quaternion.identity();
  joint.origPosition = joint.position.clone();
  joint.origQuaternion = joint.quaternion.clone();
  joint.setJointValue(Math.PI / 4);

  applyOriginToRuntimeJoint(joint, {
    xyz: { x: 0.4, y: -0.2, z: 1.1 },
    rpy: { r: 0.1, p: -0.15, y: 0.3 },
  });

  const origin = extractRuntimeJointOrigin(joint);
  assert.deepEqual(origin.xyz, { x: 0.4, y: -0.2, z: 1.1 });
  assert.ok(Math.abs(origin.rpy.r - 0.1) < 1e-6);
  assert.ok(Math.abs(origin.rpy.p + 0.15) < 1e-6);
  assert.ok(Math.abs(origin.rpy.y - 0.3) < 1e-6);
  assert.equal(joint.jointValue?.[0], Math.PI / 4);

  const expectedQuaternion = new THREE.Quaternion()
    .setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 4)
    .premultiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(0.1, -0.15, 0.3, 'ZYX')));

  assert.ok(joint.quaternion.angleTo(expectedQuaternion) < 1e-6);
});

test(
  'resolveOriginTransformClosedLoopPreview keeps Cassie achilles connect closed during origin drag',
  { concurrency: false },
  () => {
    installDomGlobals();

    const robot = parseMJCF(
      fs.readFileSync('test/mujoco_menagerie-main/agility_cassie/cassie.xml', 'utf8'),
    );
    assert.ok(robot);

    const selectedJoint = robot.joints['right-heel-spring'];
    assert.ok(selectedJoint);

    const preview = resolveOriginTransformClosedLoopPreview(robot, 'right-heel-spring', {
      ...selectedJoint.origin,
      xyz: {
        ...selectedJoint.origin.xyz,
        x: (selectedJoint.origin.xyz.x ?? 0) + 0.02,
      },
    });

    assert.ok(preview.origins['right-heel-spring']);
    assert.ok(preview.origins['right-achilles-rod']);
    assert.ok(preview.quaternions['right-achilles-rod']);
  },
);
