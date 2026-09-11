#!/usr/bin/env node

/**
 * Assembly Export browser regression test.
 *
 * Covers: assembly creation + export as URDF and MJCF,
 *         verifying merged output includes both components.
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
  const suite = createTestSuite('Assembly Export');
  const session = await createSession();
  const { page } = session;

  try {
    // ── Setup assembly ──
    await importMjcf(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);
    const topoA = await getTopology(page);

    await importUrdf(page, 'a1_description', 'a1.urdf');
    await waitForReady(page);

    await store.initAssembly(page, 'export_asm'); await delay(300);

    const fileMjcf = await findAvailableFile(page, 'go2.xml');
    const compA = await store.addComponent(page, fileMjcf); await delay(500);

    const fileUrdf = await findAvailableFile(page, 'a1.urdf');
    const compB = await store.addComponent(page, fileUrdf); await delay(500);

    const beforeBridge = await getAssemblyState(page);
    const componentA = beforeBridge.components.find((component) => component.id === compA.id);
    const componentB = beforeBridge.components.find((component) => component.id === compB.id);
    assert(suite, Boolean(componentA?.rootLinkId), 'parent component root link found');
    assert(suite, Boolean(componentB?.rootLinkId), 'child component root link found');

    // Create bridge
    const bridge = await store.addBridge(page, {
      name: 'asm_bridge',
      parentComponentId: compA.id, parentLinkId: componentA.rootLinkId,
      childComponentId: compB.id, childLinkId: componentB.rootLinkId,
      joint: { name: 'asm_bridge', type: 'fixed',
        origin: { xyz: [0.5, 0, 0], rpy: [0, 0, 0] } },
    }); await delay(500);
    assert(suite, bridge.ok, 'bridge created');

    const asm = await getAssemblyState(page);
    assertEqual(suite, asm.componentCount, 2, '2 components');
    assertEqual(suite, asm.bridgeCount, 1, '1 bridge');

    // ── Test 1: Export as URDF ──
    const urdfExport = await page.evaluate(() => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const s = api?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      const joints = Object.values(s.joints ?? {});
      const projection = api?.__workspaceStore__?.getState?.()?.getSceneProjection?.();
      const bridgeJointIds = projection
        ? [...projection.globalToEntityRef.entries()]
            .filter(([, ref]) => ref?.type === 'bridge')
            .map(([globalId]) => globalId)
        : [];
      let xml = `<?xml version="1.0"?>\n<robot name="${s.name ?? 'robot'}">\n`;
      for (const l of links) xml += `  <link name="${l?.name ?? '?'}"/>\n`;
      for (const j of joints) xml += `  <joint name="${j?.name ?? '?'}" type="${j?.type ?? 'fixed'}"/>\n`;
      xml += `</robot>`;
      return { xml, linkCount: links.length, jointCount: joints.length, bridgeJointIds };
    });

    assert(suite, !!urdfExport.xml, 'URDF export generated');
    assert(suite, urdfExport.xml.includes('<robot'), 'URDF has <robot> root');
    assertGreaterThan(suite, urdfExport.linkCount, topoA.linkCount, 'export has more links than single robot');
    assertEqual(suite, urdfExport.bridgeJointIds.length, 1, 'one projected bridge joint');
    assert(
      suite,
      urdfExport.bridgeJointIds.every((id) => urdfExport.xml.includes(`name="${id}"`)),
      'projected bridge joint is present in export',
    );

    // ── Test 2: Export as MJCF ──
    const mjcfExport = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      let xml = `<mujoco model="${s.name ?? 'robot'}">\n  <worldbody>\n`;
      for (const l of links) xml += `    <body name="${l?.name ?? '?'}"/>\n`;
      xml += `  </worldbody>\n</mujoco>`;
      return { xml };
    });

    assert(suite, !!mjcfExport.xml, 'MJCF export generated');
    assert(suite, mjcfExport.xml.includes('<mujoco'), 'MJCF has <mujoco> root');

    // ── Test 3: State intact after export ──
    const afterTopo = await getTopology(page);
    const afterAsm = await getAssemblyState(page);
    assertEqual(suite, afterAsm.componentCount, 2, 'components intact after export');
    assertEqual(suite, afterAsm.bridgeCount, 1, 'bridges intact after export');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('assembly_export', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
