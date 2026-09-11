#!/usr/bin/env node

/**
 * Cross-format Assembly browser regression test.
 *
 * Covers: assembly with MJCF + URDF components, cross-format bridge,
 *         namespace isolation, undo.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  waitForReady, getTopology, getAssemblyState, findAvailableFile,
  store, writeReport, printSummary,
} from './helpers/base-helpers.mjs';

import { importModel as importMjcf } from './helpers/mjcf-helpers.mjs';
import { importModel as importUrdf } from './helpers/urdf-helpers.mjs';

async function main() {
  const suite = createTestSuite('Cross-Format Assembly');
  const session = await createSession();
  const { page } = session;

  try {
    // ── Import MJCF model ──
    await importMjcf(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);
    const mjcfTopo = await getTopology(page);
    assertGreaterThan(suite, mjcfTopo.linkCount, 0, 'MJCF model loads');

    // ── Import URDF model ──
    await importUrdf(page, 'a1_description', 'a1.urdf');
    await waitForReady(page);

    await store.initAssembly(page, 'cross_fmt_asm'); await delay(300);
    assert(suite, (await getAssemblyState(page)).exists, 'assembly initialized');

    const fileMjcf = await findAvailableFile(page, 'go2.xml');
    const compMjcf = await store.addComponent(page, fileMjcf); await delay(500);
    assert(suite, compMjcf.ok, 'MJCF component added');

    const fileUrdf = await findAvailableFile(page, 'a1.urdf');
    const compUrdf = await store.addComponent(page, fileUrdf); await delay(500);
    assert(suite, compUrdf.ok, 'URDF component added');
    const beforeBridge = await getAssemblyState(page);
    assertEqual(suite, beforeBridge.componentCount, 2, '2 components');
    const componentMjcf = beforeBridge.components.find((component) => component.id === compMjcf.id);
    const componentUrdf = beforeBridge.components.find((component) => component.id === compUrdf.id);
    assert(suite, Boolean(componentMjcf?.rootLinkId), 'MJCF component root link found');
    assert(suite, Boolean(componentUrdf?.rootLinkId), 'URDF component root link found');

    // ── Cross-format bridge ──
    const bridge = await store.addBridge(page, {
      name: 'cross_bridge',
      parentComponentId: compMjcf.id, parentLinkId: componentMjcf.rootLinkId,
      childComponentId: compUrdf.id, childLinkId: componentUrdf.rootLinkId,
      joint: { name: 'cross_bridge', type: 'fixed',
        origin: { xyz: [1, 0, 0], rpy: [0, 0, 0] } },
    }); await delay(500);
    assert(suite, bridge.ok, 'cross-format bridge created');
    assertEqual(suite, (await getAssemblyState(page)).bridgeCount, 1, '1 bridge');

    // ── Merged topology includes both formats ──
    const mergedTopo = await getTopology(page);
    assertGreaterThan(suite, mergedTopo.linkCount, mjcfTopo.linkCount, 'merged > single MJCF');

    // ── Remove one component ──
    await store.removeComponent(page, compUrdf.id); await delay(300);
    assertEqual(suite, (await getAssemblyState(page)).componentCount, 1, 'one removed');

    // ── Full undo ──
    await store.undo(page); await delay(300);
    assertEqual(suite, (await getAssemblyState(page)).componentCount, 2, 'undo restores comp');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('cross_format_assembly', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
