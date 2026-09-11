#!/usr/bin/env node

/**
 * URDF Tree CRUD + Visibility + Undo/Redo browser regression test.
 *
 * Mirrors test_mujoco_tree_crud.mjs but uses URDF fixtures (unitree a1).
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology,
  store, writeReport, printSummary,
} from './helpers/urdf-helpers.mjs';

const MODEL = { dir: 'a1_description', file: 'a1.urdf' };

async function main() {
  const suite = createTestSuite('URDF Tree CRUD + Visibility');
  const session = await createSession();
  const { page } = session;

  try {
    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    const base = await getTopology(page);
    console.log(`  Baseline: ${base.linkCount}L ${base.jointCount}J`);

    // ── 1. AddChild + UpdateJoint ──
    const calf = base.links.find((l) => l.name === 'FL_calf');
    assert(suite, !!calf, 'FL_calf found');
    const add1 = await store.addChild(page, calf.id);
    await delay(200);
    const t1 = await getTopology(page);
    assertEqual(suite, t1.linkCount, base.linkCount + 1, 'addChild +1 link');
    assertEqual(suite, t1.jointCount, base.jointCount + 1, 'addChild +1 joint');

    const newJoint = t1.joints.find((j) => !base.joints.some((b) => b.id === j.id));
    await store.updateJoint(page, newJoint.id, {
      name: 'test_ankle', type: 'revolute',
      origin: { xyz: { x: 0, y: 0, z: -0.1 }, rpy: { r: 0, p: 0, y: 0 } },
      axis: { x: 0, y: 1, z: 0 },
      limit: { lower: -1.57, upper: 1.57, effort: 10, velocity: 5 },
    });
    await delay(200);
    const t1b = await getTopology(page);
    const uj = t1b.joints.find((j) => j.id === newJoint.id);
    assertEqual(suite, uj.name, 'test_ankle', 'joint renamed');
    assertEqual(suite, uj.type, 'revolute', 'joint type set');

    // ── 2. Add nested child then deleteSubtree ──
    const newLink = t1.links.find((l) => !base.links.some((b) => b.id === l.id));
    await store.addChild(page, newLink.id);
    await delay(200);
    const t2 = await getTopology(page);
    assertEqual(suite, t2.linkCount, t1.linkCount + 1, 'nested child +1');

    await store.deleteSubtree(page, newLink.id);
    await delay(200);
    const t3 = await getTopology(page);
    assertEqual(suite, t3.linkCount, base.linkCount, 'deleteSubtree restores count');

    // ── 3. Undo / Redo ──
    await store.undo(page); await delay(200);
    const t4 = await getTopology(page);
    assertGreaterThan(suite, t4.linkCount, t3.linkCount, 'undo restores links');

    await store.redo(page); await delay(200);
    const t5 = await getTopology(page);
    assertEqual(suite, t5.linkCount, t3.linkCount, 'redo re-deletes');

    // ── 4. Rename link ──
    const bl = t5.links.find((l) => l.name === 'base');
    await store.updateLink(page, bl.id, { name: 'base_renamed' }); await delay(200);
    const t6 = await getTopology(page);
    assertEqual(suite, t6.links.find((l) => l.id === bl.id)?.name, 'base_renamed', 'link renamed');
    await store.updateLink(page, bl.id, { name: 'base' }); // restore

    // ── 5. Rename robot ──
    await store.setName(page, 'test_robot'); await delay(200);
    const t7 = await getTopology(page);
    assertEqual(suite, t7.name, 'test_robot', 'robot renamed');
    await store.setName(page, base.name); // restore

    // ── 6. Visibility toggle ──
    const flThigh = t7.links.find((l) => l.name === 'FL_thigh');
    if (flThigh) {
      await store.setLinkVisibility(page, flThigh.id, false); await delay(200);
      const tv = await getTopology(page);
      assert(suite, tv.links.find((l) => l.id === flThigh.id)?.visible === false, 'link hidden');

      await store.setLinkVisibility(page, flThigh.id, true); await delay(200);
      const tv2 = await getTopology(page);
      assert(suite, tv2.links.find((l) => l.id === flThigh.id)?.visible !== false, 'link shown');
    }

    // ── 7. SetAllLinksVisibility ──
    await store.setAllLinksVisibility(page, false); await delay(200);
    const tAllHidden = await getTopology(page);
    assert(suite, tAllHidden.links.every((l) => l.visible === false), 'all links hidden');

    await store.setAllLinksVisibility(page, true); await delay(200);
    const tAllShown = await getTopology(page);
    assert(suite, tAllShown.links.every((l) => l.visible !== false), 'all links shown');

    // ── 8. Rapid undo ──
    for (let i = 0; i < 8; i++) { try { await store.undo(page); await delay(100); } catch {} }
    const tFinal = await getTopology(page);
    assert(suite, tFinal.linkCount > 0, 'state valid after rapid undo');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('urdf_tree_crud', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
