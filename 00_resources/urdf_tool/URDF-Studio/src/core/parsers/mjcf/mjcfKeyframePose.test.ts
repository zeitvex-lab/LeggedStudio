import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { applyInitialPoseKeyframe } from './mjcfKeyframePose';

interface TestJoint {
  origin: { xyz: { x: number; y: number; z: number }; rpy: { r: number; p: number; y: number } };
  quaternion?: { x: number; y: number; z: number; w: number };
  angle?: number;
}

function makeJoint(): TestJoint {
  return { origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } }, angle: 0 };
}

// applyInitialPoseKeyframe is typed against the real RobotState; the structural
// test doubles below satisfy only the fields it actually touches.
function apply(robot: { joints: Record<string, TestJoint> }, worldBody: unknown, keyframes: unknown) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  applyInitialPoseKeyframe(robot as any, worldBody as any, keyframes as any);
}

describe('mjcfKeyframePose', () => {
  it('is a no-op when there are no keyframes', () => {
    const joint = makeJoint();
    apply(
      { joints: { j: joint } },
      { joints: [{ name: 'j', type: 'hinge' }], children: [] },
      [],
    );
    assert.equal(joint.angle, 0);
  });

  it('applies a scalar (hinge) qpos value to joint.angle', () => {
    const joint = makeJoint();
    apply(
      { joints: { hinge0: joint } },
      { joints: [{ name: 'hinge0', type: 'hinge' }], children: [] },
      [{ name: 'home', qpos: [1.25] }],
    );
    assert.equal(joint.angle, 1.25);
  });

  it('applies a slide qpos value to joint.angle', () => {
    const joint = makeJoint();
    apply(
      { joints: { slide0: joint } },
      { joints: [{ name: 'slide0', type: 'slide' }], children: [] },
      [{ qpos: [0.5] }],
    );
    assert.equal(joint.angle, 0.5);
  });

  it('applies a free joint pose (xyz + identity quaternion) to joint.origin', () => {
    const joint = makeJoint();
    apply(
      { joints: { root: joint } },
      { joints: [{ name: 'root', type: 'free' }], children: [] },
      [{ qpos: [1, 2, 3, 1, 0, 0, 0] }],
    );
    assert.deepEqual(joint.origin.xyz, { x: 1, y: 2, z: 3 });
    // Identity quaternion -> zero rpy (tolerant of signed-zero from the ZYX conversion).
    assert.ok(Math.abs(joint.origin.rpy.r) < 1e-9);
    assert.ok(Math.abs(joint.origin.rpy.p) < 1e-9);
    assert.ok(Math.abs(joint.origin.rpy.y) < 1e-9);
  });

  it('applies a ball joint qpos quaternion to joint.quaternion', () => {
    const joint = makeJoint();
    apply(
      { joints: { ball0: joint } },
      { joints: [{ name: 'ball0', type: 'ball' }], children: [] },
      [{ qpos: [1, 0, 0, 0] }],
    );
    assert.deepEqual(joint.quaternion, { x: 0, y: 0, z: 0, w: 1 });
  });

  it('addresses nested-body joints sequentially through the qpos array', () => {
    const free = makeJoint();
    const hinge = makeJoint();
    apply(
      { joints: { root: free, elbow: hinge } },
      {
        joints: [{ name: 'root', type: 'free' }],
        children: [{ joints: [{ name: 'elbow', type: 'hinge' }], children: [] }],
      },
      // 7 free qpos slots, then the hinge value at index 7.
      [{ qpos: [0, 0, 0, 1, 0, 0, 0, 0.75] }],
    );
    assert.deepEqual(free.origin.xyz, { x: 0, y: 0, z: 0 });
    assert.equal(hinge.angle, 0.75);
  });

  it('prefers the keyframe named "home" over the first usable keyframe', () => {
    const joint = makeJoint();
    apply(
      { joints: { hinge0: joint } },
      { joints: [{ name: 'hinge0', type: 'hinge' }], children: [] },
      [
        { name: 'reset', qpos: [0.1] },
        { name: 'home', qpos: [0.9] },
      ],
    );
    assert.equal(joint.angle, 0.9);
  });

  it('skips keyframes whose qpos is shorter than the expected length', () => {
    const joint = makeJoint();
    apply(
      { joints: { root: joint } },
      { joints: [{ name: 'root', type: 'free' }], children: [] },
      // Free joint needs 7 slots; this keyframe has only 3.
      [{ qpos: [1, 2, 3] }],
    );
    assert.deepEqual(joint.origin.xyz, { x: 0, y: 0, z: 0 });
  });

  it('ignores non-finite qpos values for a free joint', () => {
    const joint = makeJoint();
    apply(
      { joints: { root: joint } },
      { joints: [{ name: 'root', type: 'free' }], children: [] },
      [{ qpos: [Number.NaN, 2, 3, 1, 0, 0, 0] }],
    );
    // A NaN translation slot aborts the free-joint write entirely.
    assert.deepEqual(joint.origin.xyz, { x: 0, y: 0, z: 0 });
  });
});
