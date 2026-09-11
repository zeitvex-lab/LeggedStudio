#!/usr/bin/env node

/**
 * Real Unitree ROS source apply strategy regression.
 *
 * Covers: small URDF link edits use incremental patches, broad source
 * replacements fall back to full parse, auto-apply still uses the same strategy,
 * and undo/redo keeps topology coherent.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, openSourceEditor,
  saveSourceEditor, waitForRobotPredicate, store,
  writeReport, printSummary, assertNoBrowserErrors,
} from './helpers/urdf-helpers.mjs';

const MODEL = { dir: 'a1_description', file: 'a1.urdf' };

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

async function readFrFootVisualRadius(page) {
  return page.evaluate(() => {
    const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
    const frFoot = snapshot?.store?.links?.find((link) => link.name === 'FR_foot') ?? null;
    return frFoot?.visual?.dimensions?.x ?? null;
  });
}

function buildLargeUrdfSource(source, rootLinkId) {
  const insertAt = source.lastIndexOf('</robot>');
  if (insertAt < 0) {
    throw new Error('Could not locate </robot> in A1 URDF source.');
  }

  const injected = Array.from({ length: 3 }, (_, index) => {
    const suffix = index + 1;
    const linkName = `codex_full_parse_link_${suffix}`;
    const jointName = `codex_full_parse_joint_${suffix}`;
    return `  <link name="${linkName}">
    <visual>
      <origin xyz="${(0.05 * suffix).toFixed(2)} 0 0.03" rpy="0 0 0"/>
      <geometry><box size="0.03 0.03 0.03"/></geometry>
      <material name="codex_full_parse_material_${suffix}">
        <color rgba="0.2 0.4 0.8 1"/>
      </material>
    </visual>
    <collision>
      <origin xyz="${(0.05 * suffix).toFixed(2)} 0 0.03" rpy="0 0 0"/>
      <geometry><box size="0.03 0.03 0.03"/></geometry>
    </collision>
  </link>
  <joint name="${jointName}" type="fixed">
    <parent link="${rootLinkId}"/>
    <child link="${linkName}"/>
    <origin xyz="${(0.05 * suffix).toFixed(2)} 0 0" rpy="0 0 0"/>
  </joint>`;
  }).join('\n');

  return `${source.slice(0, insertAt)}${injected}\n${source.slice(insertAt)}`;
}

async function runManualScenario(page, suite, report) {
  await setSourceAutoApply(page, false);
  await importModel(page, MODEL.dir, MODEL.file, 120_000);
  await waitForReady(page);
  const baseline = await getTopology(page);
  report.manualBaseline = baseline;
  assertGreaterThan(suite, baseline.linkCount, 10, 'A1 URDF baseline links loaded');
  assertGreaterThan(suite, baseline.jointCount, 10, 'A1 URDF baseline joints loaded');

  await openSourceEditor(page);
  const source = await getSourceEditorDebugText(page);
  assert(suite, source.includes('<link name="FR_foot">'), 'source editor shows raw A1 URDF');

  await replaceFirstInSourceEditor(page, 'radius="0.01"', 'radius="0.013"');
  await saveSourceEditor(page);
  await waitForRobotPredicate(
    page,
    '(snapshot) => snapshot.store.links.some((link) => link.name === "FR_foot" && Math.abs(link.visual.dimensions.x - 0.013) < 1e-6)',
    60_000,
  );

  const afterSmallRadius = await readFrFootVisualRadius(page);
  const smallApply = await getLastApplyResult(page);
  assertClose(suite, afterSmallRadius, 0.013, 'small edit updates FR_foot radius');
  assertEqual(suite, smallApply?.mode, 'incremental-patch', 'small URDF edit uses incremental patch');
  assertEqual(suite, smallApply?.patchKind, 'urdf-link-fragment-update', 'small URDF patch kind recorded');

  const largeSource = buildLargeUrdfSource(
    await getSourceEditorDebugText(page),
    baseline.rootLinkId,
  );
  await setSourceEditorDebugText(page, largeSource);
  await saveSourceEditor(page);
  await waitForRobotPredicate(
    page,
    `(snapshot) => snapshot.store.linkCount === ${baseline.linkCount + 3} && snapshot.store.links.some((link) => link.name === 'codex_full_parse_link_3')`,
    90_000,
  );

  const afterLarge = await getTopology(page);
  const largeApply = await getLastApplyResult(page);
  assertEqual(suite, afterLarge.linkCount, baseline.linkCount + 3, 'large edit adds three URDF links');
  assertEqual(suite, afterLarge.jointCount, baseline.jointCount + 3, 'large edit adds three URDF joints');
  assertEqual(suite, largeApply?.mode, 'full-parse', 'large URDF edit falls back to full parse');
  assert(suite, Boolean(largeApply?.skipReason), 'large URDF full parse records a skip reason');

  await store.undo(page);
  await waitForRobotPredicate(
    page,
    `(snapshot) => snapshot.store.linkCount === ${baseline.linkCount} && !snapshot.store.links.some((link) => link.name === 'codex_full_parse_link_1')`,
    60_000,
  );
  await store.redo(page);
  await waitForRobotPredicate(
    page,
    "(snapshot) => snapshot.store.links.some((link) => link.name === 'codex_full_parse_link_3')",
    60_000,
  );

  report.manualSmallApply = smallApply;
  report.manualLargeApply = largeApply;
  report.manualAfterLarge = afterLarge;
}

async function runAutoApplyScenario(page, suite, report) {
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), { timeout: 60_000 });
  await page.evaluate(() => {
    window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false);
  });

  await setSourceAutoApply(page, true);
  await importModel(page, MODEL.dir, MODEL.file, 120_000);
  await waitForReady(page);
  await openSourceEditor(page);
  await replaceFirstInSourceEditor(page, 'radius="0.01"', 'radius="0.014"');
  await waitForRobotPredicate(
    page,
    '(snapshot) => snapshot.store.links.some((link) => link.name === "FR_foot" && Math.abs(link.visual.dimensions.x - 0.014) < 1e-6)',
    60_000,
  );

  const autoRadius = await readFrFootVisualRadius(page);
  const autoApply = await getLastApplyResult(page);
  assertClose(suite, autoRadius, 0.014, 'auto-apply updates FR_foot radius');
  assertEqual(suite, autoApply?.mode, 'incremental-patch', 'auto-apply small URDF edit uses incremental patch');
  report.autoApply = autoApply;
}

async function main() {
  const suite = createTestSuite('Source Apply Unitree ROS');
  const session = await createSession();
  const { page } = session;
  const report = { model: MODEL };

  try {
    await runManualScenario(page, suite, report);
    await runAutoApplyScenario(page, suite, report);
    assertNoBrowserErrors(suite, session, 'source apply unitree ros');
  } finally {
    await session.cleanup();
  }

  await writeReport('source_apply_unitree_ros', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
