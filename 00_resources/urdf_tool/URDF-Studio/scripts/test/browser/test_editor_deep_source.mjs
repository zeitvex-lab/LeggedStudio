#!/usr/bin/env node

/**
 * Deep source editing browser regression.
 *
 * Covers: opening Monaco through UI, large URDF source replacement, structural
 * refresh, material preservation, invalid source recovery, undo/redo.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, getMaterialSnapshot, openSourceEditor,
  getSourceEditorText, replaceSourceEditorText, saveSourceEditor, waitForRobotPredicate,
  store, writeReport, printSummary, assertNoBrowserErrors,
} from './helpers/urdf-helpers.mjs';

const MODEL = { dir: 'a1_description', file: 'a1.urdf' };

function buildInjectedSource(source, rootLinkId) {
  const insertAt = source.lastIndexOf('</robot>');
  if (insertAt < 0) {
    throw new Error('Could not find closing </robot> tag in editable URDF source.');
  }

  const injected = Array.from({ length: 3 }, (_, index) => {
    const linkName = `codex_deep_source_link_${index + 1}`;
    const jointName = `codex_deep_source_joint_${index + 1}`;
    const x = (0.08 + index * 0.06).toFixed(3);
    const z = (0.04 + index * 0.02).toFixed(3);
    return `
  <link name="${linkName}">
    <visual>
      <origin xyz="${x} 0 ${z}" rpy="0 0 0"/>
      <geometry><box size="0.04 0.05 0.06"/></geometry>
      <material name="codex_deep_material_${index + 1}">
        <color rgba="${0.25 + index * 0.2} 0.45 0.85 1"/>
      </material>
    </visual>
    <collision>
      <origin xyz="${x} 0 ${z}" rpy="0.01 0.02 0.03"/>
      <geometry><box size="0.04 0.05 0.06"/></geometry>
    </collision>
  </link>
  <joint name="${jointName}" type="fixed">
    <parent link="${rootLinkId}"/>
    <child link="${linkName}"/>
    <origin xyz="${(0.15 + index * 0.08).toFixed(3)} 0 ${z}" rpy="0 0 0"/>
  </joint>`;
  }).join('\n');

  return `${source.slice(0, insertAt)}${injected}\n${source.slice(insertAt)}`;
}

async function readSelectedFileContent(page) {
  return page.evaluate(() => {
    const assets = window.__URDF_STUDIO_DEBUG__?.__assetsStore__?.getState?.();
    const selected = assets?.selectedFile ?? null;
    return selected?.content ?? '';
  });
}

async function main() {
  const suite = createTestSuite('Editor Deep Source');
  const session = await createSession();
  const { page } = session;
  const report = {};

  try {
    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    const baseline = await getTopology(page);
    const baselineMaterials = await getMaterialSnapshot(page);
    assertGreaterThan(suite, baseline.linkCount, 0, 'baseline model loads');

    await openSourceEditor(page);
    let source = await getSourceEditorText(page);
    if (!source.includes('</robot>')) {
      source = await readSelectedFileContent(page);
    }
    assert(suite, source.includes('</robot>'), 'source editor exposes editable robot XML');

    const modified = buildInjectedSource(source, baseline.rootLinkId);
    assertGreaterThan(suite, modified.length, source.length + 600, 'large source patch prepared');

    await replaceSourceEditorText(page, modified);
    await delay(250);
    await saveSourceEditor(page);
    await waitForRobotPredicate(
      page,
      `(snapshot) => snapshot.store.linkCount >= ${baseline.linkCount + 3} && snapshot.store.links.some((link) => link.name === 'codex_deep_source_link_3')`,
      90_000,
    );

    const afterApply = await getTopology(page);
    assertEqual(suite, afterApply.linkCount, baseline.linkCount + 3, 'source patch adds three links');
    assertEqual(suite, afterApply.jointCount, baseline.jointCount + 3, 'source patch adds three joints');

    const afterApplyMaterials = await getMaterialSnapshot(page);
    assert(
      suite,
      afterApplyMaterials.storeMaterialCount >= baselineMaterials.storeMaterialCount + 3,
      'source patch preserves existing materials and adds authored materials',
    );

    await store.undo(page);
    await waitForRobotPredicate(
      page,
      `(snapshot) => snapshot.store.linkCount === ${baseline.linkCount} && !snapshot.store.links.some((link) => link.name === 'codex_deep_source_link_1')`,
      60_000,
    );
    assertEqual(suite, (await getTopology(page)).linkCount, baseline.linkCount, 'undo reverts source patch');

    await store.redo(page);
    await waitForRobotPredicate(
      page,
      `(snapshot) => snapshot.store.links.some((link) => link.name === 'codex_deep_source_link_1')`,
      60_000,
    );
    assertEqual(suite, (await getTopology(page)).linkCount, baseline.linkCount + 3, 'redo reapplies source patch');

    const invalid = modified.replace('</robot>', '');
    await replaceSourceEditorText(page, invalid);
    await delay(250);
    await saveSourceEditor(page).catch(() => {});
    await delay(700);
    const afterInvalid = await getTopology(page);
    assertGreaterThan(suite, afterInvalid.linkCount, 0, 'invalid source does not blank the model');

    await replaceSourceEditorText(page, source);
    await delay(250);
    await saveSourceEditor(page);
    await waitForRobotPredicate(
      page,
      `(snapshot) => snapshot.store.linkCount === ${baseline.linkCount}`,
      90_000,
    );
    assertEqual(suite, (await getTopology(page)).jointCount, baseline.jointCount, 'valid source recovery restores baseline');

    assertNoBrowserErrors(suite, session, 'deep source flow');
    report.before = baseline;
    report.afterRecovery = await getTopology(page);
  } finally {
    await session.cleanup();
  }

  await writeReport('editor_deep_source', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
