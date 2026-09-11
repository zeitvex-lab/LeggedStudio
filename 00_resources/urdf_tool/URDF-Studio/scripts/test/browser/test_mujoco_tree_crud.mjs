#!/usr/bin/env node

/**
 * MuJoCo/MJCF Tree CRUD + Visibility + Undo/Redo browser regression test.
 *
 * Uses a MJCF fixture and validates topology mutations through the same store
 * paths that the tree/property editing UI exercises.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology,
  store, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

const MODEL = { dir: 'unitree_go2', file: 'go2.xml' };

function pickEditableParent(topo) {
  return (
    topo.links.find((link) => link.visualCount > 0 || link.collisionCount > 0) ??
    topo.links.find((link) => link.id === topo.rootLinkId) ??
    topo.links[0]
  );
}

function pickVisibilityTarget(topo) {
  return (
    topo.links.find((link) => link.id !== topo.rootLinkId && (link.visualCount > 0 || link.collisionCount > 0)) ??
    topo.links.find((link) => link.id !== topo.rootLinkId) ??
    topo.links[0]
  );
}

async function main() {
  const suite = createTestSuite('MuJoCo MJCF Tree CRUD + Visibility');
  const session = await createSession();
  const { page } = session;
  const report = {};

  try {
    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    const base = await getTopology(page);
    report.baseline = { linkCount: base.linkCount, jointCount: base.jointCount, name: base.name };
    console.log(`  Baseline: ${base.linkCount}L ${base.jointCount}J`);

    assertGreaterThan(suite, base.linkCount, 0, 'baseline has links');
    assertGreaterThan(suite, base.jointCount, 0, 'baseline has joints');

    // 1. Add child link/joint and update generated joint properties.
    const parent = pickEditableParent(base);
    assert(suite, !!parent, 'editable parent link selected');

    const addResult = await store.addChild(page, parent.id);
    await delay(200);
    assert(suite, addResult?.ok && Boolean(addResult.linkId) && Boolean(addResult.jointId), 'addChild returns new IDs');

    const afterAdd = await getTopology(page);
    assertEqual(suite, afterAdd.linkCount, base.linkCount + 1, 'addChild adds one link');
    assertEqual(suite, afterAdd.jointCount, base.jointCount + 1, 'addChild adds one joint');

    const addedJoint = afterAdd.joints.find((joint) => joint.id === addResult.jointId);
    const addedLink = afterAdd.links.find((link) => link.id === addResult.linkId);
    assert(suite, !!addedJoint, 'added joint appears in topology');
    assert(suite, !!addedLink, 'added link appears in topology');
    assertEqual(suite, addedJoint?.parentLinkId, parent.id, 'added joint is parented to selected link');
    assertEqual(suite, addedJoint?.childLinkId, addResult.linkId, 'added joint points to added child link');

    await store.updateJoint(page, addResult.jointId, {
      name: 'mujoco_test_joint',
      type: 'revolute',
      origin: { xyz: { x: 0.05, y: 0.1, z: -0.15 }, rpy: { r: 0.01, p: 0.02, y: 0.03 } },
      axis: { x: 0, y: 1, z: 0 },
      limit: { lower: -0.75, upper: 0.75, effort: 12, velocity: 6 },
    });
    await delay(200);

    const afterUpdate = await getTopology(page);
    const updatedJoint = afterUpdate.joints.find((joint) => joint.id === addResult.jointId);
    assertEqual(suite, updatedJoint?.name, 'mujoco_test_joint', 'generated joint renamed');
    assertEqual(suite, updatedJoint?.type, 'revolute', 'generated joint type updated');
    assertEqual(suite, updatedJoint?.axis?.[1], 1, 'generated joint axis updated');
    assertEqual(suite, updatedJoint?.limit?.upper, 0.75, 'generated joint limit updated');

    // 2. Add nested child, delete subtree, and verify undo/redo restores state.
    const nestedAdd = await store.addChild(page, addResult.linkId);
    await delay(200);
    assert(suite, nestedAdd?.ok, 'nested addChild succeeds');

    const afterNestedAdd = await getTopology(page);
    assertEqual(suite, afterNestedAdd.linkCount, base.linkCount + 2, 'nested add adds another link');
    assertEqual(suite, afterNestedAdd.jointCount, base.jointCount + 2, 'nested add adds another joint');

    await store.deleteSubtree(page, addResult.linkId);
    await delay(200);
    const afterDelete = await getTopology(page);
    assertEqual(suite, afterDelete.linkCount, base.linkCount, 'deleteSubtree restores baseline link count');
    assertEqual(suite, afterDelete.jointCount, base.jointCount, 'deleteSubtree restores baseline joint count');
    assert(suite, !afterDelete.links.some((link) => link.id === addResult.linkId), 'deleted subtree link removed');

    await store.undo(page);
    await delay(200);
    const afterUndo = await getTopology(page);
    assertEqual(suite, afterUndo.linkCount, base.linkCount + 2, 'undo restores deleted subtree links');
    assertEqual(suite, afterUndo.jointCount, base.jointCount + 2, 'undo restores deleted subtree joints');

    await store.redo(page);
    await delay(200);
    const afterRedo = await getTopology(page);
    assertEqual(suite, afterRedo.linkCount, base.linkCount, 'redo reapplies subtree deletion');
    assertEqual(suite, afterRedo.jointCount, base.jointCount, 'redo reapplies subtree joint deletion');

    // 3. Rename link and robot.
    const renameTarget = pickEditableParent(afterRedo);
    assert(suite, !!renameTarget, 'rename target selected');
    const originalLinkName = renameTarget.name;
    const renamedLinkName = `${originalLinkName || renameTarget.id}_mjcf_renamed`;
    await store.updateLink(page, renameTarget.id, { name: renamedLinkName });
    await delay(200);
    const afterLinkRename = await getTopology(page);
    assertEqual(suite, afterLinkRename.links.find((link) => link.id === renameTarget.id)?.name,
      renamedLinkName, 'link renamed');

    await store.updateLink(page, renameTarget.id, { name: originalLinkName });
    await delay(200);
    const afterLinkRestore = await getTopology(page);
    assertEqual(suite, afterLinkRestore.links.find((link) => link.id === renameTarget.id)?.name,
      originalLinkName, 'link rename restored');

    await store.setName(page, 'mujoco_tree_crud_robot');
    await delay(200);
    const afterRobotRename = await getTopology(page);
    assertEqual(suite, afterRobotRename.name, 'mujoco_tree_crud_robot', 'robot renamed');

    await store.setName(page, base.name);
    await delay(200);
    const afterRobotRestore = await getTopology(page);
    assertEqual(suite, afterRobotRestore.name, base.name, 'robot name restored');

    // 4. Per-link and global visibility toggles.
    const visibilityTarget = pickVisibilityTarget(afterRobotRestore);
    assert(suite, !!visibilityTarget, 'visibility target selected');

    await store.setLinkVisibility(page, visibilityTarget.id, false);
    await delay(200);
    const hidden = await getTopology(page);
    assert(suite, hidden.links.find((link) => link.id === visibilityTarget.id)?.visible === false, 'link hidden');

    await store.setLinkVisibility(page, visibilityTarget.id, true);
    await delay(200);
    const shown = await getTopology(page);
    assert(suite, shown.links.find((link) => link.id === visibilityTarget.id)?.visible !== false, 'link shown');

    await store.setAllLinksVisibility(page, false);
    await delay(200);
    const allHidden = await getTopology(page);
    assert(suite, allHidden.links.every((link) => link.visible === false), 'all links hidden');

    await store.setAllLinksVisibility(page, true);
    await delay(200);
    const allShown = await getTopology(page);
    assert(suite, allShown.links.every((link) => link.visible !== false), 'all links shown');

    report.final = { linkCount: allShown.linkCount, jointCount: allShown.jointCount };
    assertEqual(suite, allShown.linkCount, base.linkCount, 'final link count matches baseline');
    assertEqual(suite, allShown.jointCount, base.jointCount, 'final joint count matches baseline');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, `no page errors (${errs.page.length})`);
  } finally {
    await session.cleanup();
  }

  await writeReport('mujoco_tree_crud', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
