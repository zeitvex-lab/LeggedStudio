#!/usr/bin/env node

/**
 * MuJoCo Viewer browser regression test.
 *
 * Covers: canvas/runtime hydration, runtime transforms, display flags,
 * tool modes, projected interaction targets, and joint angle updates.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, getRuntimeTransforms,
  store, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

const MODEL = { dir: 'unitree_go2', file: 'go2.xml' };

async function getViewerSnapshot(page) {
  return page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.viewer ?? null);
}

async function getCanvasSummary(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    if (!(canvas instanceof HTMLCanvasElement)) return null;
    const rect = canvas.getBoundingClientRect();
    return {
      width: rect.width,
      height: rect.height,
      pixelWidth: canvas.width,
      pixelHeight: canvas.height,
    };
  });
}

function findTransform(transforms, namePattern) {
  return transforms.find((entry) => namePattern.test(String(entry?.name ?? ''))) ?? null;
}

async function getRuntimeRevision(page) {
  return page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.runtimeRevision ?? 0);
}

async function main() {
  const suite = createTestSuite('MuJoCo Viewer');
  let session = null;
  const report = { model: MODEL, steps: [] };

  try {
    session = await createSession();
    const { page } = session;

    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    const topo = await getTopology(page);
    report.topology = { links: topo.linkCount, joints: topo.jointCount, name: topo.name };
    assertGreaterThan(suite, topo.linkCount, 10, 'Go2 MJCF links loaded');
    assertGreaterThan(suite, topo.jointCount, 10, 'Go2 MJCF joints loaded');

    const canvas = await getCanvasSummary(page);
    report.canvas = canvas;
    assert(suite, Boolean(canvas), 'viewer canvas present');
    assertGreaterThan(suite, canvas?.width ?? 0, 300, 'canvas CSS width is usable');
    assertGreaterThan(suite, canvas?.height ?? 0, 300, 'canvas CSS height is usable');
    assertGreaterThan(suite, canvas?.pixelWidth ?? 0, 300, 'canvas backing width is usable');
    assertGreaterThan(suite, canvas?.pixelHeight ?? 0, 300, 'canvas backing height is usable');

    const initialTransforms = await getRuntimeTransforms(page);
    report.initialRuntimeLinks = initialTransforms.length;
    assertGreaterThan(suite, initialTransforms.length, 0, 'runtime link transforms present');
    assert(suite, Boolean(findTransform(initialTransforms, /base/i) ?? initialTransforms[0]), 'at least one runtime transform can be read');

    const flagResult = await store.setViewerFlags(page, {
      showCollision: true,
      showVisual: true,
      showJointAxes: true,
      showOrigins: true,
      modelOpacity: 0.65,
      highlightMode: 'collision',
    });
    assert(suite, flagResult?.ok, 'viewer display flags accepted');
    await delay(300);

    const flagSnapshot = await getViewerSnapshot(page);
    report.flags = flagSnapshot?.flags ?? null;
    assertEqual(suite, flagSnapshot?.flags?.showCollision, true, 'showCollision flag reflected in viewer snapshot');
    assertEqual(suite, flagSnapshot?.flags?.showVisual, true, 'showVisual flag reflected in viewer snapshot');
    assertEqual(suite, flagSnapshot?.flags?.showJointAxes, true, 'showJointAxes flag reflected in viewer snapshot');
    assertEqual(suite, flagSnapshot?.flags?.showOrigins, true, 'showOrigins flag reflected in viewer snapshot');
    assertEqual(suite, flagSnapshot?.flags?.highlightMode, 'collision', 'highlight mode reflected in viewer snapshot');
    assertEqual(suite, flagSnapshot?.flags?.modelOpacity, 0.65, 'model opacity reflected in viewer snapshot');

    const projectedTargets = await page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getProjectedInteractionTargets?.() ?? []);
    report.projectedTargets = projectedTargets.slice(0, 10);
    assertGreaterThan(suite, projectedTargets.length, 0, 'projected interaction targets available');
    assert(suite, projectedTargets.some((target) => target.type === 'link'), 'projected targets include links');

    for (const mode of ['paint', 'select']) {
      const result = await store.setViewerToolMode(page, mode);
      assert(suite, result?.ok, `tool mode ${mode} accepted`);
      const reflected = await page.waitForFunction(
        (expectedMode) =>
          window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.viewer?.toolMode === expectedMode,
        { timeout: 5_000 },
        result.activeMode,
      ).then(() => true).catch(() => false);
      const snapshot = await getViewerSnapshot(page);
      assert(suite, reflected, `tool mode ${mode} reflected in viewer snapshot`);
      assertEqual(suite, snapshot?.toolMode, result.activeMode, `tool mode ${mode} reflected in viewer snapshot`);
    }

    const targetJoint = topo.joints.find((joint) => joint.name === 'FL_thigh_joint') ?? topo.joints.find((joint) => joint.type === 'revolute');
    assert(suite, Boolean(targetJoint?.name), 'movable MJCF joint found');

    const beforeAngles = await getViewerSnapshot(page);
    const beforeRevision = await getRuntimeRevision(page);
    const angleResult = await store.setJointAngles(page, {
      [targetJoint.name]: -0.75,
      FL_hip_joint: 0.35,
    });
    assert(suite, angleResult?.ok, 'viewer joint angles accepted');
    assert(suite, angleResult?.changed, 'viewer joint angles report a changed state');
    await delay(500);

    const afterAngles = await getViewerSnapshot(page);
    report.jointAngles = afterAngles?.jointAngles ?? null;
    assertEqual(suite, afterAngles?.jointAngles?.[targetJoint.name], -0.75, 'target joint angle stored in viewer snapshot');
    assertEqual(suite, afterAngles?.jointAngles?.FL_hip_joint, 0.35, 'batch joint angle stored in viewer snapshot');
    assert(suite, beforeAngles?.jointAngles?.[targetJoint.name] !== afterAngles?.jointAngles?.[targetJoint.name], 'target joint angle changed from baseline');
    const afterRevision = await getRuntimeRevision(page);
    report.runtimeRevision = { before: beforeRevision, after: afterRevision };
    assertGreaterThan(suite, afterRevision, beforeRevision, 'joint angle update advances runtime revision');

    const resetFlags = await store.setViewerFlags(page, {
      showCollision: false,
      showJointAxes: false,
      showOrigins: false,
      modelOpacity: 1,
      highlightMode: 'link',
    });
    assert(suite, resetFlags?.ok, 'viewer display flags reset');

    const errs = session.errors();
    report.errors = errs;
    assert(suite, errs.page.length === 0, 'no page errors');
  } catch (error) {
    report.error = error instanceof Error ? (error.stack ?? error.message) : String(error);
    assert(suite, false, `unexpected error: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    if (session) await session.cleanup();
  }

  await writeReport('mujoco_viewer', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
