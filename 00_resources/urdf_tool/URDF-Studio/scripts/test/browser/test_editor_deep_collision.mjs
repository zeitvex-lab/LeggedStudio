#!/usr/bin/env node

/**
 * Deep collision editing browser regression.
 *
 * Covers: collision visibility, projected canvas target selection, drag frame
 * sampling, collision origin xyz/rpy edits, runtime/material preservation, undo/redo.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertGreaterThan,
  importModel, waitForReady, getRegressionSnapshot, getSemanticSnapshot,
  getMaterialSnapshot, getCanvasDiagnostics, getBestProjectedInteractionTarget,
  clickCanvasTarget, measureCanvasDrag, store, writeReport, printSummary,
  assertNoBrowserErrors,
} from './helpers/urdf-helpers.mjs';

const MODEL = { dir: 'go1_description', file: 'go1.urdf' };

function numericOrigin(origin) {
  return {
    xyz: {
      x: Number(origin?.xyz?.x ?? 0),
      y: Number(origin?.xyz?.y ?? 0),
      z: Number(origin?.xyz?.z ?? 0),
    },
    rpy: {
      r: Number(origin?.rpy?.r ?? 0),
      p: Number(origin?.rpy?.p ?? 0),
      y: Number(origin?.rpy?.y ?? 0),
    },
  };
}

function nearlyEqual(a, b, tolerance = 1e-6) {
  return Math.abs(Number(a) - Number(b)) <= tolerance;
}

function assertOriginEquals(suite, actual, expected, label) {
  const next = numericOrigin(actual);
  const prev = numericOrigin(expected);
  assert(
    suite,
    nearlyEqual(next.xyz.x, prev.xyz.x) &&
      nearlyEqual(next.xyz.y, prev.xyz.y) &&
      nearlyEqual(next.xyz.z, prev.xyz.z) &&
      nearlyEqual(next.rpy.r, prev.rpy.r) &&
      nearlyEqual(next.rpy.p, prev.rpy.p) &&
      nearlyEqual(next.rpy.y, prev.rpy.y),
    label,
  );
}

async function findPrimaryCollisionLink(page) {
  const snapshot = await getRegressionSnapshot(page);
  return snapshot?.store?.links?.find((link) =>
    link?.collision?.type && link.collision.type !== 'none') ?? null;
}

async function main() {
  const suite = createTestSuite('Editor Deep Collision');
  const session = await createSession();
  const { page } = session;
  const report = {};

  try {
    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);

    const baseSemantic = await getSemanticSnapshot(page);
    const baseMaterials = await getMaterialSnapshot(page);
    assertGreaterThan(suite, baseSemantic.robot?.linkCount ?? 0, 0, 'model loads with links');
    assertGreaterThan(
      suite,
      baseSemantic.links.filter((link) =>
        link.collision?.type && link.collision.type !== 'none').length,
      0,
      'model has editable collision geometry',
    );

    const canvas = await getCanvasDiagnostics(page);
    assert(suite, canvas.usable, 'primary canvas has usable dimensions');

    await store.setViewerFlags(page, {
      showCollision: true,
      showCollisionAlwaysOnTop: true,
      highlightMode: 'collision',
    });
    await store.setViewerToolMode(page, 'translate');
    await delay(300);

    const target = await getBestProjectedInteractionTarget(page, {
      type: 'link',
      subType: 'collision',
      targetKind: 'geometry',
    });
    assert(suite, Boolean(target), 'projected collision target is available for real canvas input');

    if (target) {
      await clickCanvasTarget(page, target);
      await delay(150);
      const interaction = await measureCanvasDrag(page, target, { x: 44, y: -28 }, { steps: 10 });
      assertGreaterThan(suite, interaction.metrics.frameCount, 10, 'collision drag samples animation frames');
      assert(
        suite,
        interaction.metrics.longFrameCount <= 3,
        `collision drag avoids excessive long frames (${interaction.metrics.longFrameCount})`,
      );
      report.dragMetrics = interaction.metrics;
    }

    const collisionLink = await findPrimaryCollisionLink(page);
    assert(suite, Boolean(collisionLink), 'primary collision link found');

    const beforeOrigin = numericOrigin(collisionLink?.collision?.origin);
    const editedOrigin = {
      xyz: {
        x: beforeOrigin.xyz.x + 0.123,
        y: beforeOrigin.xyz.y - 0.045,
        z: beforeOrigin.xyz.z + 0.067,
      },
      rpy: {
        r: beforeOrigin.rpy.r + 0.11,
        p: beforeOrigin.rpy.p - 0.07,
        y: beforeOrigin.rpy.y + 0.19,
      },
    };

    await store.updateLink(page, collisionLink.id, {
      collision: {
        ...collisionLink.collision,
        origin: editedOrigin,
      },
    });
    await delay(250);

    const editedLink = await findPrimaryCollisionLink(page);
    assertOriginEquals(suite, editedLink?.collision?.origin, editedOrigin, 'collision xyz/rpy edit committed');

    const afterEditMaterials = await getMaterialSnapshot(page);
    assert(
      suite,
      afterEditMaterials.runtimeVisualMeshCount >= baseMaterials.runtimeVisualMeshCount,
      'collision edit does not drop runtime visual meshes',
    );
    assert(
      suite,
      afterEditMaterials.runtimeMaterialCount >= baseMaterials.runtimeMaterialCount,
      'collision edit does not drop runtime material bindings',
    );

    await store.undo(page);
    await delay(250);
    const undoLink = await findPrimaryCollisionLink(page);
    assertOriginEquals(suite, undoLink?.collision?.origin, beforeOrigin, 'undo restores collision origin');

    await store.redo(page);
    await delay(250);
    const redoLink = await findPrimaryCollisionLink(page);
    assertOriginEquals(suite, redoLink?.collision?.origin, editedOrigin, 'redo reapplies collision origin');

    assertNoBrowserErrors(suite, session, 'deep collision flow');
    report.semantic = await getSemanticSnapshot(page);
    report.materials = await getMaterialSnapshot(page);
  } finally {
    await session.cleanup();
  }

  await writeReport('editor_deep_collision', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
