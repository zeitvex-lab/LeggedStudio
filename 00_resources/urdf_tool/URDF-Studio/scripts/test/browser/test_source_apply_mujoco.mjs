#!/usr/bin/env node

/**
 * Real MuJoCo source apply strategy regression.
 *
 * Covers: small MJCF body edits use incremental patches, broad source
 * replacements fall back to full parse, and undo/redo keeps topology coherent.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, openSourceEditor, saveSourceEditor,
  waitForRobotPredicate, store,
  writeReport, printSummary, assertNoBrowserErrors,
} from './helpers/mjcf-helpers.mjs';

const MODEL = { dir: 'unitree_go2', file: 'go2.xml' };

function assertClose(suite, actual, expected, label) {
  assert(
    suite,
    Number.isFinite(actual) && Math.abs(actual - expected) < 1e-6,
    `${label}: expected ${expected}, received ${actual}`,
  );
}

async function setSourceAutoApply(page, enabled) {
  await page.evaluate((nextEnabled) => {
    window.__URDF_STUDIO_DEBUG__?.__uiStore__?.setState?.({
      sourceCodeAutoApply: nextEnabled,
    });
  }, enabled);
}

async function replaceFirstInSourceEditor(page, fromText, toText) {
  await page.waitForFunction(
    () => Boolean(window.__URDF_STUDIO_DEBUG__?.__sourceEditor?.replaceFirst),
    { timeout: 45_000 },
  );
  const result = await page.evaluate(
    ({ from, to }) => {
      return window.__URDF_STUDIO_DEBUG__?.__sourceEditor?.replaceFirst?.(from, to) ?? {
        ok: false,
        error: 'source editor debug API is unavailable',
      };
    },
    { from: fromText, to: toText },
  );
  if (!result?.ok) {
    throw new Error(result?.error || `Source text not found: ${fromText}`);
  }
  await delay(100);
}

async function getSourceEditorDebugText(page) {
  await page.waitForFunction(
    () => Boolean(window.__URDF_STUDIO_DEBUG__?.__sourceEditor?.getValue),
    { timeout: 45_000 },
  );
  return page.evaluate(() => window.__URDF_STUDIO_DEBUG__.__sourceEditor.getValue());
}

async function setSourceEditorDebugText(page, value) {
  await page.waitForFunction(
    () => Boolean(window.__URDF_STUDIO_DEBUG__?.__sourceEditor?.setValue),
    { timeout: 45_000 },
  );
  const result = await page.evaluate(
    (nextValue) => window.__URDF_STUDIO_DEBUG__.__sourceEditor.setValue(nextValue),
    value,
  );
  if (!result?.ok) {
    throw new Error('Failed to replace source editor text.');
  }
  await delay(100);
}

async function getLastApplyResult(page) {
  return page.evaluate(() =>
    window.__URDF_STUDIO_DEBUG__?.getLastEditableSourceApplyResult?.() ?? null);
}

async function readGo2SourceState(page) {
  return page.evaluate(() => {
    const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
    const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.() ?? null;
    const joints = snapshot?.store?.joints ?? [];
    const flHipJoint = joints.find((joint) => joint.name === 'FL_hip_joint') ?? null;
    const runtimeLinks = Array.isArray(runtime?.links) ? runtime.links : [];
    const runtimeFlHip = runtimeLinks.find(
      (link) => link?.name === 'FL_hip',
    ) ?? null;

    return {
      jointOriginX: flHipJoint?.origin?.xyz?.x ?? null,
      runtimeX: Array.isArray(runtimeFlHip?.position) ? runtimeFlHip.position[0] : null,
      runtimeLinkCount: runtimeLinks.length,
    };
  });
}

function buildLargeMjcfSource(source) {
  const insertAt = source.lastIndexOf('</worldbody>');
  if (insertAt < 0) {
    throw new Error('Could not locate </worldbody> in Go2 MJCF source.');
  }

  const injected = Array.from({ length: 3 }, (_, index) => {
    const suffix = index + 1;
    return `    <body name="codex_full_parse_body_${suffix}" pos="${(0.05 * suffix).toFixed(2)} 0 0.02">
      <geom type="sphere" size="0.01" rgba="0.2 0.4 0.8 1"/>
    </body>`;
  }).join('\n');

  return `${source.slice(0, insertAt)}${injected}\n  ${source.slice(insertAt)}`;
}

async function main() {
  const suite = createTestSuite('Source Apply MuJoCo');
  const session = await createSession();
  const { page } = session;
  const report = { model: MODEL };

  try {
    await setSourceAutoApply(page, false);
    await importModel(page, MODEL.dir, MODEL.file, 120_000);
    await waitForReady(page);
    const baseline = await getTopology(page);
    report.baseline = baseline;
    assertGreaterThan(suite, baseline.linkCount, 10, 'Go2 MJCF baseline links loaded');
    assertGreaterThan(suite, baseline.jointCount, 10, 'Go2 MJCF baseline joints loaded');

    await openSourceEditor(page);
    const source = await getSourceEditorDebugText(page);
    assert(suite, source.includes('<mujoco model="go2"'), 'source editor shows Go2 MJCF');

    await replaceFirstInSourceEditor(
      page,
      'pos="0.1934 0.0465 0"',
      'pos="0.2034 0.0465 0"',
    );
    await saveSourceEditor(page);
    await waitForRobotPredicate(
      page,
      '(snapshot) => snapshot.store.joints.some((joint) => joint.name === "FL_hip_joint" && Math.abs(joint.origin.xyz.x - 0.2034) < 1e-6)',
      60_000,
    );

    const afterSmall = await readGo2SourceState(page);
    const smallApply = await getLastApplyResult(page);
    assertClose(suite, afterSmall.jointOriginX, 0.2034, 'small edit updates store joint origin');
    assertEqual(suite, smallApply?.mode, 'incremental-patch', 'small MJCF edit uses incremental patch');
    assertEqual(suite, smallApply?.patchKind, 'mjcf-body-subtree-update', 'small MJCF patch kind recorded');

    const largeSource = buildLargeMjcfSource(await getSourceEditorDebugText(page));
    await setSourceEditorDebugText(page, largeSource);
    await saveSourceEditor(page);
    await waitForRobotPredicate(
      page,
      `(snapshot) => snapshot.store.linkCount >= ${baseline.linkCount + 3} && snapshot.store.links.some((link) => link.name === 'codex_full_parse_body_3')`,
      90_000,
    );

    const afterLarge = await getTopology(page);
    const largeApply = await getLastApplyResult(page);
    assertEqual(suite, afterLarge.linkCount, baseline.linkCount + 3, 'large edit adds three MJCF bodies');
    assertEqual(suite, largeApply?.mode, 'full-parse', 'large MJCF edit falls back to full parse');
    assert(suite, Boolean(largeApply?.skipReason), 'large MJCF full parse records a skip reason');

    await store.undo(page);
    await waitForRobotPredicate(
      page,
      `(snapshot) => snapshot.store.linkCount === ${baseline.linkCount} && !snapshot.store.links.some((link) => link.name === 'codex_full_parse_body_1')`,
      60_000,
    );
    await store.redo(page);
    await waitForRobotPredicate(
      page,
      "(snapshot) => snapshot.store.links.some((link) => link.name === 'codex_full_parse_body_3')",
      60_000,
    );

    report.afterSmall = afterSmall;
    report.smallApply = smallApply;
    report.afterLarge = afterLarge;
    report.largeApply = largeApply;
    assertNoBrowserErrors(suite, session, 'source apply mujoco');
  } finally {
    await session.cleanup();
  }

  await writeReport('source_apply_mujoco', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
