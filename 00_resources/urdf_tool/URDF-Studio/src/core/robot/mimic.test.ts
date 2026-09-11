import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_JOINT, JointType, type RobotState } from '@/types';

import { resolveMimicJointAngleTargets } from './mimic.ts';

function assertAlmostEqual(actual: number, expected: number, epsilon = 1e-9): void {
  assert.ok(
    Math.abs(actual - expected) <= epsilon,
    `expected ${actual} to be within ${epsilon} of ${expected}`,
  );
}

test('resolveMimicJointAngleTargets inverts the selected mimic chain and propagates explicit angles', () => {
  const robot = {
    joints: {
      leader: {
        ...DEFAULT_JOINT,
        id: 'leader',
        name: 'leader',
        type: JointType.REVOLUTE,
      },
      follower: {
        ...DEFAULT_JOINT,
        id: 'follower',
        name: 'follower',
        type: JointType.REVOLUTE,
        mimic: {
          joint: 'leader',
          multiplier: 2,
          offset: 0.1,
        },
      },
      tip: {
        ...DEFAULT_JOINT,
        id: 'tip',
        name: 'tip',
        type: JointType.REVOLUTE,
        mimic: {
          joint: 'follower',
          multiplier: -0.5,
          offset: 0.2,
        },
      },
    },
  } satisfies Pick<RobotState, 'joints'>;

  const resolved = resolveMimicJointAngleTargets(robot, 'tip', 0.3);

  assert.equal(resolved.driverJointId, 'leader');
  assertAlmostEqual(resolved.driverAngle, -0.15);
  assertAlmostEqual(resolved.angles.leader ?? NaN, -0.15);
  assertAlmostEqual(resolved.angles.follower ?? NaN, -0.2);
  assertAlmostEqual(resolved.angles.tip ?? NaN, 0.3);
  assert.deepEqual(new Set(resolved.lockedJointIds), new Set(['leader', 'follower', 'tip']));
});
