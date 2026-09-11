import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { JSDOM } from 'jsdom';
import * as THREE from 'three';

import { parseMJCF } from '@/core/parsers/mjcf/mjcfParser.ts';
import { computeLinkWorldMatrices } from '@/core/robot/kinematics.ts';

import type { ClosedLoopDrivenJointMotionResult } from '@/core/robot/closedLoops.ts';
import type { RobotState } from '@/types';

import {
  createClosedLoopMotionPreviewSession,
  createClosedLoopMotionPreviewWorkerSession,
} from './closedLoopMotionPreview.ts';

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

function computeClosedLoopPreviewResidual(
  robot: Pick<RobotState, 'links' | 'joints' | 'rootLinkId' | 'closedLoopConstraints'>,
  preview: {
    angles: Record<string, number>;
    quaternions: Record<string, any>;
  },
): number {
  const linkWorldMatrices = computeLinkWorldMatrices(robot, {
    angles: preview.angles,
    quaternions: preview.quaternions,
  });
  let residualSquared = 0;

  (robot.closedLoopConstraints ?? []).forEach((constraint) => {
    const anchorA = new THREE.Vector3(
      constraint.anchorLocalA.x,
      constraint.anchorLocalA.y,
      constraint.anchorLocalA.z,
    ).applyMatrix4(linkWorldMatrices[constraint.linkAId]);
    const anchorB = new THREE.Vector3(
      constraint.anchorLocalB.x,
      constraint.anchorLocalB.y,
      constraint.anchorLocalB.z,
    ).applyMatrix4(linkWorldMatrices[constraint.linkBId]);
    const error =
      constraint.type === 'distance'
        ? Math.abs(anchorA.distanceTo(anchorB) - constraint.restDistance)
        : anchorA.distanceTo(anchorB);
    residualSquared += error * error;
  });

  return Math.sqrt(residualSquared);
}

test(
  'createClosedLoopMotionPreviewSession projects the active Robotiq coupler angle into the feasible loop range',
  { concurrency: false },
  () => {
    installDomGlobals();

    const robot = parseMJCF(
      fs.readFileSync('test/mujoco_menagerie-main/robotiq_2f85/2f85.xml', 'utf8'),
    );
    assert.ok(robot);

    const session = createClosedLoopMotionPreviewSession();
    session.setBaseRobot(robot);

    const preview = session.solve('right_coupler_joint', -1.57);

    assert.equal(preview.constrained, true);
    assert.ok(
      typeof preview.appliedAngle === 'number' && preview.appliedAngle > -0.8,
      `expected preview to report a constrained applied angle near the feasible boundary, angle=${preview.appliedAngle}`,
    );
    assert.ok(typeof preview.angles.right_coupler_joint === 'number');
    assert.ok(
      (preview.angles.right_coupler_joint ?? 0) > -0.8,
      `expected right_coupler_joint preview to move toward the feasible boundary, angle=${preview.angles.right_coupler_joint}`,
    );
    assert.ok(
      (preview.angles.right_coupler_joint ?? 0) < -0.3,
      `expected right_coupler_joint preview to clamp near the feasible boundary, angle=${preview.angles.right_coupler_joint}`,
    );
    assert.ok(
      typeof preview.angles.right_driver_joint === 'number' &&
        (preview.angles.right_driver_joint ?? 0) > 0.2,
      `expected right_driver_joint preview to be driven by the closed-loop solve, angle=${preview.angles.right_driver_joint}`,
    );
    assert.ok(
      Math.abs((preview.angles.right_follower_joint ?? 0) - 0.872664) < 1e-6,
      `expected right_follower_joint preview to reach its feasible boundary, angle=${preview.angles.right_follower_joint}`,
    );
  },
);

test(
  'createClosedLoopMotionPreviewSession closes Cassie preview constraints to editor tolerance',
  { concurrency: false },
  () => {
    installDomGlobals();

    const robot = parseMJCF(
      fs.readFileSync('test/mujoco_menagerie-main/agility_cassie/cassie.xml', 'utf8'),
    );
    assert.ok(robot);

    const session = createClosedLoopMotionPreviewSession();
    session.setBaseRobot(robot);

    const preview = session.solve('left-knee', -1.2);
    const residual = computeClosedLoopPreviewResidual(robot, preview);

    assert.ok(
      residual < 1e-5,
      `expected Cassie preview residual below editor tolerance, residual=${residual}`,
    );
  },
);

test('createClosedLoopMotionPreviewWorkerSession applies async worker results to preview state', async () => {
  const robot = {
    links: {
      base: { id: 'base', name: 'base' },
      link: { id: 'link', name: 'link' },
      follower_link: { id: 'follower_link', name: 'follower_link' },
    },
    joints: {
      hinge: {
        id: 'hinge',
        name: 'hinge',
        type: 'revolute',
        parentLinkId: 'base',
        childLinkId: 'link',
        axis: { x: 0, y: 0, z: 1 },
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      },
      follower: {
        id: 'follower',
        name: 'follower',
        type: 'revolute',
        parentLinkId: 'base',
        childLinkId: 'follower_link',
        axis: { x: 0, y: 0, z: 1 },
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      },
    },
    rootLinkId: 'base',
    closedLoopConstraints: [],
  } as any;
  const session = createClosedLoopMotionPreviewWorkerSession(
    async (_robot, jointId, angle): Promise<ClosedLoopDrivenJointMotionResult> => ({
      angles: {
        [jointId]: angle,
        follower: angle * 2,
      },
      quaternions: {},
      appliedAngle: angle,
      requestedAngle: angle,
      constrained: true,
      constraintErrors: {},
      residual: 0,
      iterations: 1,
      converged: true,
    }),
  );

  session.setBaseRobot(robot);
  const preview = await session.solve('hinge', 0.25);

  assert.equal(preview.appliedAngle, 0.25);
  assert.equal(preview.constrained, true);
  assert.deepEqual(preview.angles, {
    hinge: 0.25,
    follower: 0.5,
  });
});

test('createClosedLoopMotionPreviewWorkerSession reuses the base robot and sends preview deltas', async () => {
  const robot = {
    links: {
      base: { id: 'base', name: 'base' },
      link: { id: 'link', name: 'link' },
      follower_link: { id: 'follower_link', name: 'follower_link' },
    },
    joints: {
      hinge: {
        id: 'hinge',
        name: 'hinge',
        type: 'revolute',
        parentLinkId: 'base',
        childLinkId: 'link',
        axis: { x: 0, y: 0, z: 1 },
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        angle: 0,
      },
      follower: {
        id: 'follower',
        name: 'follower',
        type: 'revolute',
        parentLinkId: 'base',
        childLinkId: 'follower_link',
        axis: { x: 0, y: 0, z: 1 },
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        angle: 0,
      },
    },
    rootLinkId: 'base',
    closedLoopConstraints: [],
  } as any;
  const calls: Array<{
    robot: typeof robot;
    jointId: string;
    angle: number;
    options?: { maxIterations?: number; tolerance?: number; damping?: number };
    previewState: {
      angles: Record<string, number>;
      quaternions: Record<string, any>;
    };
  }> = [];
  const session = createClosedLoopMotionPreviewWorkerSession(
    async (
      solveRobot,
      jointId,
      angle,
      options,
      previewState = { angles: {}, quaternions: {} },
    ): Promise<ClosedLoopDrivenJointMotionResult> => {
      calls.push({ robot: solveRobot as typeof robot, jointId, angle, options, previewState });
      return {
        angles: {
          [jointId]: angle,
          follower: angle * 2,
        },
        quaternions: {},
        appliedAngle: angle,
        requestedAngle: angle,
        constrained: false,
        constraintErrors: {},
        residual: 0,
        iterations: 1,
        converged: true,
      };
    },
  );

  session.setBaseRobot(robot);
  await session.solve('hinge', 0.25);
  await session.solve('hinge', 0.5);

  assert.equal(calls.length, 2);
  assert.equal(calls[0].robot, robot);
  assert.equal(calls[1].robot, robot);
  assert.deepEqual(calls[0].options, { maxIterations: 12, tolerance: 1e-5 });
  assert.deepEqual(calls[1].options, { maxIterations: 12, tolerance: 1e-5 });
  assert.deepEqual(calls[0].previewState, { angles: {}, quaternions: {} });
  assert.deepEqual(calls[1].previewState, {
    angles: {
      hinge: 0.25,
      follower: 0.5,
    },
    quaternions: {},
  });
});
