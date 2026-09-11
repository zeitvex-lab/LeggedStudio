import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_JOINT, DEFAULT_LINK } from '@/types';
import type { RobotState } from '@/types';

import {
  applyJointInteractionPreviewToRobot,
  type JointInteractionPreviewLike,
} from './jointInteractionPreview.ts';

const robotFixture: RobotState = {
  name: 'preview-fixture',
  rootLinkId: 'base_link',
  selection: { type: 'joint', id: 'joint_a' },
  links: {
    base_link: {
      ...DEFAULT_LINK,
      id: 'base_link',
      name: 'base_link',
    },
    child_link: {
      ...DEFAULT_LINK,
      id: 'child_link',
      name: 'child_link',
    },
  },
  joints: {
    joint_a: {
      ...DEFAULT_JOINT,
      id: 'joint_a',
      name: 'joint_a',
      parentLinkId: 'base_link',
      childLinkId: 'child_link',
      angle: 0,
      origin: {
        xyz: { x: 0, y: 0, z: 0.5 },
        rpy: { r: 0, p: 0, y: 0 },
      },
    },
  },
};

test('applyJointInteractionPreviewToRobot returns the original robot when preview is empty', () => {
  const preview: JointInteractionPreviewLike = {
    jointAngles: {},
    jointQuaternions: {},
    jointOrigins: {},
  };

  assert.equal(applyJointInteractionPreviewToRobot(robotFixture, preview), robotFixture);
});

test('applyJointInteractionPreviewToRobot overlays transient joint motion and origin data', () => {
  const previewOrigin = {
    xyz: { x: 0.2, y: -0.1, z: 0.75 },
    rpy: { r: 0.3, p: -0.2, y: 0.15 },
  };
  const previewQuaternion = { x: 0.1, y: 0.2, z: -0.3, w: 0.9 };
  const preview: JointInteractionPreviewLike = {
    jointAngles: { joint_a: 0.42 },
    jointQuaternions: { joint_a: previewQuaternion },
    jointOrigins: { joint_a: previewOrigin },
  };

  const overlayRobot = applyJointInteractionPreviewToRobot(robotFixture, preview);

  assert.notEqual(overlayRobot, robotFixture);
  assert.notEqual(overlayRobot.joints, robotFixture.joints);
  assert.equal(overlayRobot.selection, robotFixture.selection);
  assert.equal(overlayRobot.joints.joint_a?.angle, 0.42);
  assert.equal(overlayRobot.joints.joint_a?.quaternion, previewQuaternion);
  assert.equal(overlayRobot.joints.joint_a?.origin, previewOrigin);
  assert.equal(robotFixture.joints.joint_a?.angle, 0, 'base robot should remain unchanged');
});
