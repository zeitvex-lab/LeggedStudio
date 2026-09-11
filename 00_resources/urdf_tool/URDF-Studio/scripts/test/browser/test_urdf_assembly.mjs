#!/usr/bin/env node

/**
 * URDF Assembly browser regression test.
 *
 * Covers: initAssembly, addComponent (URDF), bridge creation,
 *         merged topology verification, undo/redo.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, getAssemblyState, findAvailableFile,
  store, writeReport, printSummary,
} from './helpers/urdf-helpers.mjs';

const ROBOT_A = { dir: 'a1_description', file: 'a1.urdf' };
const ROBOT_B = { dir: 'go1_description', file: 'go1.urdf' };

async function main() {
  const suite = createTestSuite('URDF Assembly');
  const session = await createSession();
  const { page } = session;

  try {
    await importModel(page, ROBOT_A.dir, ROBOT_A.file);
    await waitForReady(page);
    const topoA = await getTopology(page);
    assertGreaterThan(suite, topoA.linkCount, 0, 'robot A loads');

    await importModel(page, ROBOT_B.dir, ROBOT_B.file);
    await waitForReady(page);

    await store.initAssembly(page, 'test_urdf_asm'); await delay(300);
    assert(suite, (await getAssemblyState(page)).exists, 'assembly initialized');

    const fileA = await findAvailableFile(page, ROBOT_A.file);
    const compA = await store.addComponent(page, fileA); await delay(500);
    assertGreaterThan(suite, (await getAssemblyState(page)).componentCount, 0, 'comp A added');

    const fileB = await findAvailableFile(page, ROBOT_B.file);
    const compB = await store.addComponent(page, fileB); await delay(500);
    const beforeBridge = await getAssemblyState(page);
    assertEqual(suite, beforeBridge.componentCount, 2, 'comp B added');
    const componentA = beforeBridge.components.find((component) => component.id === compA.id);
    const componentB = beforeBridge.components.find((component) => component.id === compB.id);
    assert(suite, Boolean(componentA?.rootLinkId), 'component A root link found');
    assert(suite, Boolean(componentB?.rootLinkId), 'component B root link found');

    // Create bridge
    const bridge = await store.addBridge(page, {
      name: 'urdf_bridge_1',
      parentComponentId: compA.id, parentLinkId: componentA.rootLinkId,
      childComponentId: compB.id, childLinkId: componentB.rootLinkId,
      joint: { name: 'urdf_bridge_1', type: 'fixed',
        origin: { xyz: [0.5, 0, 0], rpy: [0, 0, 0] } },
    }); await delay(500);
    assert(suite, bridge.ok, 'bridge created');
    assertEqual(suite, (await getAssemblyState(page)).bridgeCount, 1, '1 bridge');

    // Update bridge type
    await store.updateBridge(page, bridge.id, { joint: { name: 'urdf_bridge_1_upd', type: 'revolute' } });
    await delay(200);
    const updatedBridge = (await getAssemblyState(page)).bridges.find((entry) => entry.id === bridge.id);
    assertEqual(suite, updatedBridge?.name, 'urdf_bridge_1_upd', 'bridge renamed');
    assertEqual(suite, updatedBridge?.jointType, 'revolute', 'bridge type updated');

    // Merged topology > single robot
    assertGreaterThan(suite, (await getTopology(page)).linkCount, topoA.linkCount, 'merged > single');

    // Undo bridge update, then undo bridge creation.
    await store.undo(page); await delay(300);
    const restoredBridge = (await getAssemblyState(page)).bridges.find((entry) => entry.id === bridge.id);
    assertEqual(suite, restoredBridge?.name, 'urdf_bridge_1', 'undo restores bridge name');
    assertEqual(suite, restoredBridge?.jointType, 'fixed', 'undo restores bridge type');

    await store.undo(page); await delay(300);
    assertEqual(suite, (await getAssemblyState(page)).bridgeCount, 0, 'second undo removes bridge');

    // Remove component
    await store.removeComponent(page, compB.id); await delay(300);
    assertEqual(suite, (await getAssemblyState(page)).componentCount, 1, 'comp removed');

    // Undo removal
    await store.undo(page); await delay(300);
    assertEqual(suite, (await getAssemblyState(page)).componentCount, 2, 'undo restores comp');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('urdf_assembly', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
