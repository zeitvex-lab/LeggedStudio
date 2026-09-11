#!/usr/bin/env node

/**
 * MuJoCo Assembly browser regression test.
 *
 * Covers: two MJCF components, bridge creation/update, merged topology,
 * component transforms, and undo for bridge and component operations.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, getAssemblyState, findAvailableFile,
  store, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

const GO2 = { dir: 'unitree_go2', file: 'go2.xml' };
const PANDA = { dir: 'franka_emika_panda', file: 'panda.xml' };
const IMPORT_TIMEOUT_MS = 120_000;

async function main() {
  const suite = createTestSuite('MuJoCo Assembly');
  let session = null;
  const report = { models: [GO2, PANDA], steps: [] };

  try {
    session = await createSession();
    const { page } = session;

    await importModel(page, GO2.dir, GO2.file, IMPORT_TIMEOUT_MS);
    await waitForReady(page);
    const go2Topo = await getTopology(page);
    report.go2 = { links: go2Topo.linkCount, joints: go2Topo.jointCount, name: go2Topo.name };
    assertGreaterThan(suite, go2Topo.linkCount, 10, 'Go2 MJCF model loads');
    assertGreaterThan(suite, go2Topo.jointCount, 10, 'Go2 MJCF joints load');

    await importModel(page, PANDA.dir, PANDA.file, IMPORT_TIMEOUT_MS);
    await waitForReady(page);
    const pandaTopo = await getTopology(page);
    report.panda = { links: pandaTopo.linkCount, joints: pandaTopo.jointCount, name: pandaTopo.name };
    assertGreaterThan(suite, pandaTopo.linkCount, 5, 'Panda MJCF model loads');
    assertGreaterThan(suite, pandaTopo.jointCount, 5, 'Panda MJCF joints load');

    await store.initAssembly(page, 'mujoco_assembly_regression');
    await delay(300);
    const initialized = await getAssemblyState(page);
    assert(suite, initialized.exists, 'assembly initialized');

    const go2File = await findAvailableFile(page, GO2.file);
    assert(suite, Boolean(go2File?.content), 'Go2 MJCF file available for assembly');
    const go2Component = await store.addComponent(page, go2File);
    await delay(700);
    assert(suite, go2Component.ok, 'Go2 MJCF component added');

    const pandaFile = await findAvailableFile(page, PANDA.file);
    assert(suite, Boolean(pandaFile?.content), 'Panda MJCF file available for assembly');
    const pandaComponent = await store.addComponent(page, pandaFile);
    await delay(700);
    assert(suite, pandaComponent.ok, 'Panda MJCF component added');

    const beforeBridge = await getAssemblyState(page);
    report.beforeBridge = beforeBridge;
    assertEqual(suite, beforeBridge.componentCount, 2, 'two MJCF components in assembly');

    const go2Entry = beforeBridge.components.find((component) => component.id === go2Component.id);
    const pandaEntry = beforeBridge.components.find((component) => component.id === pandaComponent.id);
    assert(suite, Boolean(go2Entry?.rootLinkId), 'Go2 component root link found');
    assert(suite, Boolean(pandaEntry?.rootLinkId), 'Panda component root link found');
    assert(suite, /go2\.xml$/i.test(go2Entry?.sourceFile ?? ''), 'Go2 component source file tracked');
    assert(suite, /panda\.xml$/i.test(pandaEntry?.sourceFile ?? ''), 'Panda component source file tracked');

    await store.updateComponentTransform(page, pandaComponent.id, {
      position: { x: 0.85, y: 0.15, z: 0.25 },
      rotation: { r: 0, p: 0, y: 0.35 },
    });
    await delay(300);
    const transformUpdated = await getAssemblyState(page);
    assertEqual(suite, transformUpdated.componentCount, 2, 'component transform preserves component count');

    const bridge = await store.addBridge(page, {
      name: 'mujoco_bridge_go2_panda',
      parentComponentId: go2Component.id,
      parentLinkId: go2Entry.rootLinkId,
      childComponentId: pandaComponent.id,
      childLinkId: pandaEntry.rootLinkId,
      joint: {
        name: 'mujoco_bridge_go2_panda',
        type: 'fixed',
        origin: { xyz: [0.85, 0.15, 0.25], rpy: [0, 0, 0.35] },
      },
    });
    await delay(700);
    assert(suite, bridge.ok, 'MJCF bridge created');

    const bridged = await getAssemblyState(page);
    report.bridged = bridged;
    assertEqual(suite, bridged.bridgeCount, 1, 'one bridge in MJCF assembly');
    assertEqual(suite, bridged.bridges[0]?.jointType, 'fixed', 'bridge starts fixed');

    const mergedTopo = await getTopology(page);
    report.merged = { links: mergedTopo.linkCount, joints: mergedTopo.jointCount };
    assertGreaterThan(suite, mergedTopo.linkCount, Math.max(go2Topo.linkCount, pandaTopo.linkCount), 'merged MJCF topology exceeds either component');
    assertGreaterThan(suite, mergedTopo.jointCount, Math.max(go2Topo.jointCount, pandaTopo.jointCount), 'merged MJCF joints exceed either component');
    assertEqual(suite, mergedTopo.linkCount, go2Topo.linkCount + pandaTopo.linkCount, 'merged links equal both MJCF components');
    assertEqual(suite, mergedTopo.jointCount, go2Topo.jointCount + pandaTopo.jointCount + 1, 'merged joints include both components plus bridge');

    await store.updateBridge(page, bridge.id, {
      joint: {
        name: 'mujoco_bridge_revolute',
        type: 'revolute',
        axis: { x: 0, y: 0, z: 1 },
        limit: { lower: -0.25, upper: 0.25, effort: 25, velocity: 5 },
      },
    });
    await delay(300);
    const updatedBridge = (await getAssemblyState(page)).bridges.find((entry) => entry.id === bridge.id);
    assertEqual(suite, updatedBridge?.name, 'mujoco_bridge_revolute', 'bridge rename applied');
    assertEqual(suite, updatedBridge?.jointType, 'revolute', 'bridge joint type updated');

    await store.undo(page);
    await delay(400);
    const restoredBridge = (await getAssemblyState(page)).bridges.find((entry) => entry.id === bridge.id);
    assertEqual(suite, restoredBridge?.name, 'mujoco_bridge_go2_panda', 'undo restores bridge name');
    assertEqual(suite, restoredBridge?.jointType, 'fixed', 'undo restores bridge type');

    await store.undo(page);
    await delay(400);
    assertEqual(suite, (await getAssemblyState(page)).bridgeCount, 0, 'second undo removes bridge');

    await store.removeComponent(page, pandaComponent.id);
    await delay(300);
    assertEqual(suite, (await getAssemblyState(page)).componentCount, 1, 'component removal applies');

    await store.undo(page);
    await delay(400);
    assertEqual(suite, (await getAssemblyState(page)).componentCount, 2, 'undo restores removed MJCF component');

    const errs = session.errors();
    report.errors = errs;
    assert(suite, errs.page.length === 0, 'no page errors');
  } catch (error) {
    report.error = error instanceof Error ? (error.stack ?? error.message) : String(error);
    assert(suite, false, `unexpected error: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    if (session) await session.cleanup();
  }

  await writeReport('mujoco_assembly', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
