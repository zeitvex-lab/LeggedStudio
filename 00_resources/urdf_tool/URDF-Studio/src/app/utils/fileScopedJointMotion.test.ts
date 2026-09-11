import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyRememberedFileJointMotion,
  captureRememberedFileJointMotion,
  type FileJointMotionMemory,
} from './fileScopedJointMotion.ts';

function createRobotJoint(options: {
  id: string;
  name?: string;
  angle?: number;
  quaternion?: { x: number; y: number; z: number; w: number };
}) {
  return {
    ...options,
    type: 'revolute',
  };
}

function createRobotData(joints: Record<string, ReturnType<typeof createRobotJoint>>) {
  return {
    name: 'demo_robot',
    links: {},
    joints,
    rootLinkId: 'base_link',
  };
}

test('does not persist transient joint motion across file switches', () => {
  const existingMemory: FileJointMotionMemory = {
    'robots/other.urdf': {
      shoulder_joint: { angle: 0.4 },
    },
  };

  const nextMemory = captureRememberedFileJointMotion('robots/a.urdf', createRobotData({
    shoulder_a: createRobotJoint({
      id: 'shoulder_a',
      name: 'shoulder_joint',
      angle: 1.25,
    }),
  }), existingMemory);

  assert.equal(nextMemory, existingMemory);
  assert.deepEqual(nextMemory, {
    'robots/other.urdf': {
      shoulder_joint: { angle: 0.4 },
    },
  });
});

test('reopening a robot keeps authored defaults instead of replaying remembered joint data', () => {
  const restoredRobot = applyRememberedFileJointMotion('robots/demo.urdf', createRobotData({
    runtime_joint_key: createRobotJoint({
      id: 'runtime_joint_key',
      name: 'shoulder_joint',
      angle: 0,
    }),
  }), {
    'robots/demo.urdf': {
      shoulder_joint: {
        angle: 0.75,
        quaternion: { x: 0, y: 0, z: 0.5, w: 0.8660254037844386 },
      },
    },
  });

  assert.equal(restoredRobot.joints.runtime_joint_key.angle, 0);
  assert.equal(restoredRobot.joints.runtime_joint_key.quaternion, undefined);
});

test('keeps authored defaults when there is no remembered motion for the file', () => {
  const restoredRobot = applyRememberedFileJointMotion('robots/missing.urdf', createRobotData({
    shoulder_joint: createRobotJoint({
      id: 'shoulder_joint',
      name: 'shoulder_joint',
      angle: 0.2,
    }),
  }), {});

  assert.equal(restoredRobot.joints.shoulder_joint.angle, 0.2);
});
