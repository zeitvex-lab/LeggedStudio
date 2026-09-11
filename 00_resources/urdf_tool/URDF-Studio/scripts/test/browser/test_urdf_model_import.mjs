#!/usr/bin/env node

/**
 * URDF Model Import browser regression test.
 *
 * Verifies import, topology, and basic structure for multiple URDF fixtures
 * from test/unitree_ros/robots/.
 */

import {
  createSession, createTestSuite, assert, assertGreaterThan, assertNonNull,
  importModel, waitForReady, getTopology,
  writeReport, printSummary,
} from './helpers/urdf-helpers.mjs';

const MODELS = [
  { dir: 'a1_description',  file: 'a1.urdf' },
  { dir: 'go1_description', file: 'go1.urdf' },
  { dir: 'go2_description', file: 'go2_description.urdf' },
];

async function main() {
  const suite = createTestSuite('URDF Model Import');
  const session = await createSession();
  const results = [];

  try {
    for (const { dir, file } of MODELS) {
      console.log(`\n── ${dir}/${file} ──`);

      try {
        const loadedName = await importModel(session.page, dir, file);
        await waitForReady(session.page);
        const topo = await getTopology(session.page);

        // Basic topology
        assertGreaterThan(suite, topo.linkCount, 0, `${dir}: links > 0 (${topo.linkCount})`);
        assertGreaterThan(suite, topo.jointCount, 0, `${dir}: joints > 0 (${topo.jointCount})`);
        assertNonNull(suite, topo.name, `${dir}: robot name present`);
        assertNonNull(suite, topo.rootLinkId, `${dir}: rootLinkId present`);

        // Joint types
        const revoluteCount = topo.joints.filter((j) => j.type === 'revolute').length;
        const fixedCount = topo.joints.filter((j) => j.type === 'fixed').length;
        assertGreaterThan(suite, revoluteCount + fixedCount, 0, `${dir}: has revolute/fixed joints`);

        // Inertial data
        const withInertial = topo.links.filter((l) => l.inertial !== null).length;
        assertGreaterThan(suite, withInertial, 0, `${dir}: links with inertial > 0`);

        const loadState = await session.page.evaluate(() =>
          window.__URDF_STUDIO_DEBUG__?.getDocumentLoadState?.());
        assert(suite, loadState?.fileName === loadedName, `${dir}: document state tracks loaded file`);

        // Visual/collision bodies on non-trivial links
        const linksWithVisual = topo.links.filter((l) => l.visualCount > 0);
        assertGreaterThan(suite, linksWithVisual.length, 0, `${dir}: links with visual bodies`);

        results.push({ model: dir, status: 'ok', linkCount: topo.linkCount, jointCount: topo.jointCount, name: topo.name });
      } catch (err) {
        assert(suite, false, `${dir}: import succeeded — ${err.message}`);
        results.push({ model: dir, status: 'error', error: err.message });
      }
    }

    const errs = session.errors();
    assert(suite, errs.page.length === 0, `no page errors (${errs.page.length})`);
  } finally {
    await session.cleanup();
  }

  await writeReport('urdf_model_import', { results });
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
