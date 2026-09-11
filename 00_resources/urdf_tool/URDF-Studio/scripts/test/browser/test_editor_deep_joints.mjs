#!/usr/bin/env node

/**
 * Deep joint editing browser regression.
 *
 * Covers: all joint type values, origin/axis/limit/dynamics edits, joint angle
 * preview, display helpers, undo/redo topology safety.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, getRegressionSnapshot,
  store, writeReport, printSummary, assertNoBrowserErrors,
} from './helpers/urdf-helpers.mjs';

const MODEL = { dir: 'go1_description', file: 'go1.urdf' };
const JOINT_TYPES = ['fixed', 'revolute', 'continuous', 'prismatic', 'planar', 'floating'];

function findTargetJoint(snapshot) {
  return snapshot?.store?.joints?.find((joint) => joint.type === 'revolute') ??
    snapshot?.store?.joints?.[0] ??
    null;
}

async function currentJoint(page, jointId) {
  const snapshot = await getRegressionSnapshot(page);
  return snapshot?.store?.joints?.find((joint) => joint.id === jointId) ?? null;
}

async function main() {
  const suite = createTestSuite('Editor Deep Joints');
  const session = await createSession();
  const { page } = session;
  const report = { jointTypes: [] };

  try {
    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    const baseline = await getTopology(page);
    assertGreaterThan(suite, baseline.jointCount, 0, 'baseline model has joints');

    await store.setViewerFlags(page, {
      showJointAxes: true,
      showJointAxesOverlay: true,
      showOrigins: true,
      showOriginsOverlay: true,
    });
    await store.setViewerToolMode(page, 'rotate');
    await delay(300);

    const target = findTargetJoint(await getRegressionSnapshot(page));
    assert(suite, Boolean(target), 'target joint selected for matrix edits');

    for (const type of JOINT_TYPES) {
      await store.updateJoint(page, target.id, {
        type,
        axis: { x: 0, y: 1, z: 0 },
        origin: {
          xyz: { x: 0.012, y: -0.023, z: 0.034 },
          rpy: { r: 0.05, p: -0.04, y: 0.03 },
        },
        limit: type === 'continuous' || type === 'fixed'
          ? undefined
          : { lower: -0.42, upper: 0.42, effort: 12, velocity: 3 },
        dynamics: { damping: 0.8, friction: 0.12 },
      });
      await delay(180);
      const edited = await currentJoint(page, target.id);
      assertEqual(suite, edited?.type, type, `joint type ${type} committed`);
      assertEqual(suite, edited?.axis?.y, 1, `joint axis y committed for ${type}`);
      assertEqual(suite, edited?.origin?.xyz?.x, 0.012, `joint origin xyz committed for ${type}`);
      assertEqual(suite, edited?.dynamics?.damping, 0.8, `joint damping committed for ${type}`);
      report.jointTypes.push({ type, limit: edited?.limit ?? null });
    }

    const revoluteUpdate = {
      type: 'revolute',
      axis: { x: 1, y: 0, z: 0 },
      origin: {
        xyz: { x: 0.031, y: 0.022, z: -0.011 },
        rpy: { r: 0.02, p: 0.03, y: -0.04 },
      },
      limit: { lower: -1.1, upper: 1.1, effort: 20, velocity: 8 },
      dynamics: { damping: 1.2, friction: 0.25 },
    };
    await store.updateJoint(page, target.id, revoluteUpdate);
    await delay(250);

    const angleResult = await store.setJointAngle(page, target.name, 0.37);
    assert(suite, angleResult?.ok, 'single joint angle preview accepted');
    const batchResult = await store.setJointAngles(page, {
      [target.name]: -0.18,
      FL_hip_joint: 0.12,
      FR_hip_joint: -0.12,
    });
    assert(suite, batchResult?.ok, 'batch joint angle preview accepted');
    await delay(250);

    const postPreviewSnapshot = await getRegressionSnapshot(page);
    const documentState = await page.evaluate(() =>
      window.__URDF_STUDIO_DEBUG__?.getDocumentLoadState?.() ?? null);
    assertGreaterThan(
      suite,
      postPreviewSnapshot?.store?.jointCount ?? 0,
      0,
      'store summary remains available after joint edits',
    );
    assert(suite, documentState?.status !== 'error', 'document state is not errored after joint edits');

    const afterMatrix = await getTopology(page);
    assertEqual(suite, afterMatrix.linkCount, baseline.linkCount, 'joint edits preserve link count');
    assertEqual(suite, afterMatrix.jointCount, baseline.jointCount, 'joint edits preserve joint count');

    await store.undo(page);
    await delay(250);
    const undoJoint = await currentJoint(page, target.id);
    assert(
      suite,
      undoJoint?.dynamics?.damping !== 1.2 || undoJoint?.origin?.xyz?.x !== 0.031,
      'undo backs out last joint matrix edit',
    );

    await store.redo(page);
    await delay(250);
    const redoJoint = await currentJoint(page, target.id);
    assertEqual(suite, redoJoint?.type, 'revolute', 'redo restores revolute type');
    assertEqual(suite, redoJoint?.limit?.upper, 1.1, 'redo restores joint limits');

    assertNoBrowserErrors(suite, session, 'deep joints flow');
    report.finalTopology = await getTopology(page);
  } finally {
    await session.cleanup();
  }

  await writeReport('editor_deep_joints', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
