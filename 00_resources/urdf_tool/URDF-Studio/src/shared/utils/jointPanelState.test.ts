import test from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizeViewerJointAngleState,
  resolveViewerJointAngleValue,
  resolveViewerJointKey,
} from './jointPanelState.ts';

const runtimeJoints = {
  runtime_joint_elbow: {
    id: 'runtime_joint_elbow',
    name: 'elbow_joint',
    angle: 0.25,
  },
  runtime_joint_wrist: {
    id: 'runtime_joint_wrist',
    name: 'wrist_joint',
    angle: -0.4,
  },
};

test('resolveViewerJointKey accepts both runtime ids and authored joint names', () => {
  assert.equal(resolveViewerJointKey(runtimeJoints, 'runtime_joint_elbow'), 'runtime_joint_elbow');
  assert.equal(resolveViewerJointKey(runtimeJoints, 'elbow_joint'), 'runtime_joint_elbow');
  assert.equal(resolveViewerJointKey(runtimeJoints, 'missing_joint'), null);
});

test('normalizeViewerJointAngleState rewrites authored joint-name keys to runtime ids', () => {
  assert.deepEqual(
    normalizeViewerJointAngleState(runtimeJoints, {
      elbow_joint: 1.2,
      wrist_joint: -0.6,
      missing_joint: 0.8,
    }),
    {
      runtime_joint_elbow: 1.2,
      runtime_joint_wrist: -0.6,
    },
  );
});

test('resolveViewerJointAngleValue falls back from runtime id to authored joint name and joint angle', () => {
  assert.equal(
    resolveViewerJointAngleValue({ elbow_joint: 1.2 }, 'runtime_joint_elbow', runtimeJoints.runtime_joint_elbow),
    1.2,
  );
  assert.equal(
    resolveViewerJointAngleValue({}, 'runtime_joint_wrist', runtimeJoints.runtime_joint_wrist),
    -0.4,
  );
  assert.equal(
    resolveViewerJointAngleValue({}, 'missing_joint', { name: 'missing_joint' }),
    0,
  );
});
