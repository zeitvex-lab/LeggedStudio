#!/usr/bin/env node

/**
 * Deep material preservation browser regression.
 *
 * Covers: URDF/MJCF/SDF/USD/Xacro import, display toggles, visual color edit
 * where editable, material/runtime snapshots, undo.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertGreaterThan,
  getRegressionSnapshot, getMaterialSnapshot, getSemanticSnapshot,
  store, writeReport, printSummary, assertNoBrowserErrors,
} from './helpers/base-helpers.mjs';
import { importModel as importUrdf, waitForReady as waitUrdfReady } from './helpers/urdf-helpers.mjs';
import { importModel as importMjcf } from './helpers/mjcf-helpers.mjs';
import { importModel as importSdf } from './helpers/sdf-helpers.mjs';
import { importUnitreeModel } from './helpers/usd-helpers.mjs';
import { importModel as importXacro } from './helpers/xacro-helpers.mjs';

const CASES = [
  {
    label: 'URDF a1',
    editable: true,
    importModel: (page) => importUrdf(page, 'a1_description', 'a1.urdf'),
  },
  {
    label: 'MJCF go2',
    editable: true,
    importModel: (page) => importMjcf(page, 'unitree_go2', 'go2.xml'),
  },
  {
    label: 'SDF bus_stop',
    editable: false,
    importModel: (page) => importSdf(page, 'bus_stop', 'model.sdf'),
  },
  {
    label: 'USD Go2',
    editable: false,
    importModel: (page) => importUnitreeModel(page, 'Go2', 180_000),
  },
  {
    label: 'Xacro a1',
    editable: true,
    importModel: (page) => importXacro(page, 'a1_description/xacro/robot.xacro', 'robot.xacro'),
  },
];

function firstEditableVisualLink(snapshot) {
  return snapshot?.store?.links?.find((link) => link?.visual?.type && link.visual.type !== 'none') ?? null;
}

async function runCase(suite, page, testCase) {
  console.log(`\n── ${testCase.label} ──`);
  await testCase.importModel(page);
  await waitUrdfReady(page, 180_000);

  const semantic = await getSemanticSnapshot(page);
  const beforeMaterials = await getMaterialSnapshot(page);
  assertGreaterThan(suite, semantic.robot?.linkCount ?? 0, 0, `${testCase.label}: semantic links present`);
  assertGreaterThan(
    suite,
    beforeMaterials.runtimeVisualMeshCount + (semantic.usdScene?.meshDescriptorCount ?? 0),
    0,
    `${testCase.label}: visual mesh or USD descriptor material surface present`,
  );

  await store.setViewerFlags(page, {
    showVisual: true,
    showCollision: true,
    showCollisionAlwaysOnTop: true,
    modelOpacity: 0.72,
  });
  await delay(350);

  const afterToggle = await getMaterialSnapshot(page);
  assert(
    suite,
    afterToggle.runtimeVisualMeshCount >= beforeMaterials.runtimeVisualMeshCount,
    `${testCase.label}: display toggles preserve visual mesh count`,
  );
  assert(
    suite,
    afterToggle.runtimeMaterialCount >= beforeMaterials.runtimeMaterialCount,
    `${testCase.label}: display toggles preserve runtime material count`,
  );

  if (testCase.editable) {
    const snapshot = await getRegressionSnapshot(page);
    const link = firstEditableVisualLink(snapshot);
    assert(suite, Boolean(link), `${testCase.label}: editable visual link found`);
    if (link) {
      const previousColor = link.visual?.color ?? null;
      await store.updateLink(page, link.id, {
        visual: {
          ...link.visual,
          color: '#3366ff',
          materialSource: link.visual?.materialSource ?? 'inline',
        },
      });
      await delay(300);
      const editedMaterials = await getMaterialSnapshot(page);
      const editedRecord = editedMaterials.storeMaterials.find((material) => material.linkId === link.id);
      assert(
        suite,
        editedRecord?.color === '#3366ff',
        `${testCase.label}: visual color edit reaches material snapshot`,
      );
      assert(
        suite,
        editedMaterials.runtimeVisualMeshCount >= beforeMaterials.runtimeVisualMeshCount,
        `${testCase.label}: color edit preserves runtime visual meshes`,
      );

      await store.undo(page);
      await delay(250);
      const restored = await getRegressionSnapshot(page);
      const restoredLink = restored?.store?.links?.find((entry) => entry.id === link.id);
      assert(
        suite,
        (restoredLink?.visual?.color ?? null) === previousColor,
        `${testCase.label}: undo restores previous visual color`,
      );
    }
  } else if (semantic.usdScene) {
    assert(
      suite,
      semantic.usdScene.materialCount > 0 || afterToggle.usdMaterials?.meshes?.length > 0,
      `${testCase.label}: USD material summary remains available`,
    );
  }

  return {
    label: testCase.label,
    semantic,
    materials: await getMaterialSnapshot(page),
  };
}

async function main() {
  const suite = createTestSuite('Editor Deep Materials');
  const session = await createSession();
  const { page } = session;
  const results = [];

  try {
    for (const testCase of CASES) {
      try {
        results.push(await runCase(suite, page, testCase));
      } catch (error) {
        assert(suite, false, `${testCase.label}: material flow completed — ${error.message}`);
      }
    }

    assertNoBrowserErrors(suite, session, 'deep materials flow');
  } finally {
    await session.cleanup();
  }

  await writeReport('editor_deep_materials', { results });
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
