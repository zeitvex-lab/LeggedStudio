#!/usr/bin/env node

/**
 * URDF Property Editor browser regression test.
 *
 * Covers: joint origin/axis/limit/dynamics editing, joint type change,
 *         joint angle control, display flags, tool mode switching.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual,
  importModel, waitForReady, getTopology,
  getCanvasDiagnostics, measureInteractionFrames,
  measureCanvasContinuityDuring,
  store, writeReport, printSummary,
} from './helpers/urdf-helpers.mjs';

const MODEL = { dir: 'go1_description', file: 'go1.urdf' };

async function waitForRuntimeStable(page, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  let lastStableKey = null;
  let stableSamples = 0;
  let lastProbe = null;

  while (Date.now() < deadline) {
    const probe = await page.evaluate(() => ({
      snapshot: window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null,
      assets: window.__URDF_STUDIO_DEBUG__?.getAssetDebugState?.() ?? null,
    }));
    const { snapshot, assets } = probe;
    lastProbe = probe;
    const revision = snapshot?.primaryRuntimeRevision ?? snapshot?.runtimeRevision;
    const runtime = snapshot?.primaryRuntime ?? snapshot?.runtime;
    const appAssetCount = assets?.appAssetKeys?.length ?? 0;
    const scopedAssetCount = assets?.viewerScopedAssetKeys?.length ?? 0;
    const scopeReady = appAssetCount === 0 || scopedAssetCount > 0;
    const storeLinkCount = snapshot?.store?.linkCount ?? 0;
    const storeJointCount = snapshot?.store?.jointCount ?? 0;
    const runtimeLinkCount = runtime?.linkCount ?? 0;
    const runtimeJointCount = runtime?.jointCount ?? 0;
    const topologyReady =
      storeJointCount > 0
        ? runtimeJointCount >= storeJointCount
        : storeLinkCount === 0 || runtimeLinkCount >= storeLinkCount;
    const stableKey = JSON.stringify({
      revision,
      scopeSignature: assets?.viewerScopedSignature ?? null,
      scopedAssetCount,
      runtimeName: runtime?.name ?? null,
      runtimeLinkCount,
      runtimeJointCount,
    });

    if (runtime && Number.isFinite(revision) && scopeReady && topologyReady) {
      if (stableKey === lastStableKey) {
        stableSamples += 1;
      } else {
        lastStableKey = stableKey;
        stableSamples = 1;
      }
      if (stableSamples >= 8) {
        return snapshot;
      }
    } else {
      lastStableKey = null;
      stableSamples = 0;
    }
    await delay(150);
  }

  throw new Error(`Timed out waiting for stable runtime: ${JSON.stringify(lastProbe)}`);
}

async function assertNoRuntimeReloadDuring(suite, page, label, action) {
  const before = await waitForRuntimeStable(page);
  assert(
    suite,
    Boolean(before?.primaryRuntime ?? before?.runtime),
    `${label}: runtime exists before edit`,
  );
  const beforeRevision = before?.primaryRuntimeRevision ?? before?.runtimeRevision;
  const canvasBefore = await getCanvasDiagnostics(page);
  assert(suite, canvasBefore.usable, `${label}: canvas usable before edit`);

  const { actionResult, metrics } = await measureInteractionFrames(page, action, {
    durationMs: 700,
  });
  assert(
    suite,
    actionResult?.ok !== false && !actionResult?.error,
    `${label}: edit action completed`,
  );
  await delay(100);

  const after = await waitForRuntimeStable(page);
  const afterRevision = after?.primaryRuntimeRevision ?? after?.runtimeRevision;
  const canvasAfter = await getCanvasDiagnostics(page);
  assertEqual(suite, afterRevision, beforeRevision, `${label}: runtime did not reload`);
  assert(
    suite,
    Boolean(after?.primaryRuntime ?? after?.runtime),
    `${label}: runtime exists after edit`,
  );
  assert(suite, canvasAfter.usable, `${label}: canvas usable after edit`);
  assert(
    suite,
    metrics.longFrameCount <= 2,
    `${label}: no repeated long frames during edit (count=${metrics.longFrameCount})`,
  );
}

async function assertGlobalUpdateDoesNotBlankCanvas(suite, page, label, action) {
  const before = await waitForRuntimeStable(page);
  const beforeRevision = before?.primaryRuntimeRevision ?? before?.runtimeRevision;
  assert(suite, Number.isFinite(beforeRevision), `${label}: runtime revision exists before update`);

  const { actionResult, metrics } = await measureCanvasContinuityDuring(page, action, {
    durationMs: 1_700,
  });
  assert(
    suite,
    actionResult?.ok !== false && !actionResult?.error,
    `${label}: global update action completed`,
  );
  assert(
    suite,
    metrics.sampleCount >= 3,
    `${label}: sampled canvas during global update (${metrics.sampleCount})`,
  );
  assertEqual(
    suite,
    metrics.missingRuntimeFrameCount,
    0,
    `${label}: runtime stayed mounted during global update`,
  );
  assertEqual(
    suite,
    metrics.blankFrameCount,
    0,
    `${label}: canvas did not blank during global update`,
  );

  const after = await waitForRuntimeStable(page, 30_000);
  const afterRevision = after?.primaryRuntimeRevision ?? after?.runtimeRevision;
  assert(
    suite,
    Number(afterRevision) > Number(beforeRevision),
    `${label}: structural update completed with a new runtime`,
  );
  return metrics;
}

async function getEditableVisualLinks(page) {
  return page.evaluate(() => {
    const links = window.__URDF_STUDIO_DEBUG__?.__workspaceStore__
      ?.getState?.()
      ?.getSceneProjection?.()
      ?.robotData?.links ?? {};
    return Object.values(links)
      .filter((link) => link?.id !== 'base' && link?.visual?.type && link.visual.type !== 'none')
      .slice(0, 2);
  });
}

async function main() {
  const suite = createTestSuite('URDF Property Editor');
  const session = await createSession();
  const { page } = session;
  const report = {};

  try {
    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    await waitForRuntimeStable(page);
    const base = await getTopology(page);
    console.log(`  Baseline: ${base.linkCount}L ${base.jointCount}J`);

    // ── 1. Joint origin editing ──
    const hipJoint = base.joints.find((j) => j.name === 'FL_hip_joint');
    assert(suite, !!hipJoint, 'FL_hip_joint found');

    await assertNoRuntimeReloadDuring(suite, page, 'joint origin edit', () =>
      store.updateJoint(page, hipJoint.id, {
        origin: { xyz: { x: 0.1, y: 0.2, z: 0.3 }, rpy: { r: 0.1, p: 0.2, y: 0.3 } },
      }),
    );
    const t1 = await getTopology(page);
    const j1 = t1.joints.find((j) => j.id === hipJoint.id);
    assertEqual(suite, j1.originXyz?.[0], 0.1, 'joint origin xyz[0] updated');

    const visualLinks = await getEditableVisualLinks(page);
    assert(suite, visualLinks.length >= 2, 'at least two visual links found');

    await assertNoRuntimeReloadDuring(suite, page, 'link visual color edit', () =>
      store.updateLink(page, visualLinks[0].id, {
        visual: { ...visualLinks[0].visual, color: '#12ab34' },
      }),
    );

    await assertNoRuntimeReloadDuring(suite, page, 'multi-link visual color edit', async () => {
      const first = await store.updateLink(page, visualLinks[0].id, {
        visual: { ...visualLinks[0].visual, color: '#22c55e' },
      });
      const second = await store.updateLink(page, visualLinks[1].id, {
        visual: { ...visualLinks[1].visual, color: '#3b82f6' },
      });
      return { ok: first.ok && second.ok };
    });

    // Restore the first link color so later undo checks do not depend on these
    // visual-only edits.
    await store.updateLink(page, visualLinks[0].id, {
      visual: visualLinks[0].visual,
    });
    await delay(200);

    // Restore
    await store.updateJoint(page, hipJoint.id, {
      origin: {
        xyz: { x: hipJoint.originXyz[0], y: hipJoint.originXyz[1], z: hipJoint.originXyz[2] },
        rpy: { r: hipJoint.originRpy[0], p: hipJoint.originRpy[1], y: hipJoint.originRpy[2] },
      },
    });
    await waitForRuntimeStable(page);

    // ── 2. Joint axis editing ──
    await assertNoRuntimeReloadDuring(suite, page, 'joint axis edit', () =>
      store.updateJoint(page, hipJoint.id, { axis: { x: 0, y: 1, z: 0 } }),
    );
    const t2 = await getTopology(page);
    const j2 = t2.joints.find((j) => j.id === hipJoint.id);
    assertEqual(suite, j2.axis?.[1], 1, 'joint axis updated');

    // Restore
    await store.updateJoint(page, hipJoint.id, {
      axis: { x: hipJoint.axis[0], y: hipJoint.axis[1], z: hipJoint.axis[2] },
    });
    await waitForRuntimeStable(page);

    // ── 3. Joint limit editing ──
    await assertNoRuntimeReloadDuring(suite, page, 'joint limit edit', () =>
      store.updateJoint(page, hipJoint.id, {
        limit: { lower: -0.5, upper: 0.5, effort: 20, velocity: 10 },
      }),
    );
    const t3 = await getTopology(page);
    const j3 = t3.joints.find((j) => j.id === hipJoint.id);
    assertEqual(suite, j3.limit?.lower, -0.5, 'joint limit.lower updated');
    assertEqual(suite, j3.limit?.upper, 0.5, 'joint limit.upper updated');

    // ── 4. Joint dynamics editing ──
    await assertNoRuntimeReloadDuring(suite, page, 'joint dynamics edit', () =>
      store.updateJoint(page, hipJoint.id, {
        dynamics: { damping: 5, friction: 0.5 },
      }),
    );
    const t4 = await getTopology(page);
    const j4 = t4.joints.find((j) => j.id === hipJoint.id);
    assertEqual(suite, j4.damping, 5, 'joint damping updated');
    assertEqual(suite, j4.friction, 0.5, 'joint friction updated');

    // ── 5. Joint type change ──
    await assertNoRuntimeReloadDuring(suite, page, 'joint type edit', () =>
      store.updateJoint(page, hipJoint.id, { type: 'continuous' }),
    );
    const t5 = await getTopology(page);
    assertEqual(suite, t5.joints.find((j) => j.id === hipJoint.id)?.type, 'continuous', 'joint type → continuous');

    // Undo to restore
    await store.undo(page); await waitForRuntimeStable(page);
    const t5b = await getTopology(page);
    assertEqual(suite, t5b.joints.find((j) => j.id === hipJoint.id)?.type, 'revolute', 'joint type restored');

    // ── 6. Joint angle control ──
    const angleResult = await store.setJointAngle(page, 'FL_hip_joint', 0.5);
    assert(suite, angleResult?.ok, 'setJointAngle ok');
    await delay(200);

    // Batch joint angles
    const batchResult = await store.setJointAngles(page, { 'FL_hip_joint': 0.3, 'FR_hip_joint': -0.3 });
    assert(suite, batchResult?.ok, 'setJointAngles batch ok');
    await delay(200);

    // ── 7. Display flags toggle ──
    const flagResult = await store.setViewerFlags(page, { showCollision: true });
    assert(suite, flagResult?.ok, 'setViewerFlags showCollision ok');
    await delay(200);

    const flagsOff = await store.setViewerFlags(page, { showCollision: false });
    assert(suite, flagsOff?.ok, 'setViewerFlags showCollision off ok');

    // ── 8. Tool mode switching ──
    const translateMode = await store.setViewerToolMode(page, 'translate');
    assert(suite, translateMode?.ok, 'tool mode → translate');
    await delay(200);

    const selectMode = await store.setViewerToolMode(page, 'select');
    assert(suite, selectMode?.ok, 'tool mode → select');

    // ── 9. Structural global update keeps old scene visible until handoff ──
    report.globalUpdateContinuity = await assertGlobalUpdateDoesNotBlankCanvas(
      suite,
      page,
      'structural add-child global update',
      () => store.addChild(page, base.rootLinkId),
    );
    const afterStructuralUpdate = await getTopology(page);
    assert(
      suite,
      afterStructuralUpdate.linkCount === base.linkCount + 1,
      'structural add-child updates topology',
    );
    await store.undo(page);
    await waitForRuntimeStable(page, 30_000);

    // ── 10. Undo property changes, verify topology intact ──
    // Undo several times to revert limit/dynamics changes
    for (let i = 0; i < 5; i++) { try { await store.undo(page); await delay(100); } catch {} }
    const tFinal = await getTopology(page);
    assert(suite, tFinal.linkCount === base.linkCount, 'topology intact after undo');
    assert(suite, tFinal.jointCount === base.jointCount, 'joints intact after undo');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('urdf_property_editor', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
