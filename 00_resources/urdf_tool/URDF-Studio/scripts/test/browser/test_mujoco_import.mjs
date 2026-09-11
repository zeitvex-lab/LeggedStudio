#!/usr/bin/env node

/**
 * MuJoCo/MJCF Model Import browser regression test.
 *
 * Verifies MJCF directory upload, selected document metadata, topology,
 * root/name, joint types, and visual/collision bodies for representative
 * MuJoCo menagerie fixtures.
 */

import {
  createSession, createTestSuite, assert, assertGreaterThan, assertNonNull,
  importModel, waitForReady, getTopology,
  writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

const MODELS = [
  { dir: 'unitree_go2', file: 'go2.xml' },
  { dir: 'franka_emika_panda', file: 'panda.xml' },
];

async function readLoadState(page) {
  return page.evaluate(() => {
    const api = window.__URDF_STUDIO_DEBUG__;
    const snapshot = api?.getRegressionSnapshot?.() ?? null;
    return {
      selectedFile: snapshot?.selectedFile ?? null,
      document: api?.getDocumentLoadState?.() ?? null,
      runtime: snapshot?.runtime
        ? {
            linkCount: snapshot.runtime.linkCount,
            jointCount: snapshot.runtime.jointCount,
            visualMeshCount: snapshot.runtime.visualMeshCount,
            collisionMeshCount: snapshot.runtime.collisionMeshCount,
          }
        : null,
    };
  });
}

function basename(value) {
  return String(value ?? '').split('/').filter(Boolean).pop() ?? '';
}

async function main() {
  const suite = createTestSuite('MuJoCo MJCF Import');
  const session = await createSession();
  const results = [];

  try {
    for (const { dir, file } of MODELS) {
      console.log(`\n-- ${dir}/${file} --`);

      try {
        const loadedName = await importModel(session.page, dir, file);
        await waitForReady(session.page);
        const topo = await getTopology(session.page);
        const loadState = await readLoadState(session.page);

        assertGreaterThan(suite, topo.linkCount, 0, `${dir}: links > 0 (${topo.linkCount})`);
        assertGreaterThan(suite, topo.jointCount, 0, `${dir}: joints > 0 (${topo.jointCount})`);
        assertNonNull(suite, topo.name, `${dir}: robot name present`);
        assertNonNull(suite, topo.rootLinkId, `${dir}: rootLinkId present`);
        assert(suite, topo.links.some((link) => link.id === topo.rootLinkId), `${dir}: root link exists in topology`);

        const jointTypes = [...new Set(topo.joints.map((joint) => joint.type).filter(Boolean))].sort();
        assertGreaterThan(suite, jointTypes.length, 0, `${dir}: has parsed joint types (${jointTypes.join(', ')})`);
        assert(suite, topo.joints.every((joint) => Boolean(joint.name) && Boolean(joint.parentLinkId) && Boolean(joint.childLinkId)),
          `${dir}: joints have names and parent/child links`);

        const linksWithVisual = topo.links.filter((link) => link.visualCount > 0);
        const linksWithCollision = topo.links.filter((link) => link.collisionCount > 0);
        assert(suite, linksWithVisual.length + linksWithCollision.length > 0,
          `${dir}: links include visual or collision bodies`);

        assert(suite, basename(loadState.selectedFile?.name) === file, `${dir}: selected file tracks ${file}`);
        assert(suite, loadState.selectedFile?.format === 'mjcf', `${dir}: selected file format is mjcf`);
        assert(suite, basename(loadState.document?.fileName) === basename(loadedName),
          `${dir}: document state tracks loaded file`);
        assert(suite, loadState.document?.format === 'mjcf', `${dir}: document load format is mjcf`);

        results.push({
          model: dir,
          status: 'ok',
          loadedName,
          name: topo.name,
          rootLinkId: topo.rootLinkId,
          linkCount: topo.linkCount,
          jointCount: topo.jointCount,
          jointTypes,
          linksWithVisual: linksWithVisual.length,
          linksWithCollision: linksWithCollision.length,
          runtime: loadState.runtime,
        });
      } catch (err) {
        assert(suite, false, `${dir}: import succeeded - ${err.message}`);
        results.push({ model: dir, status: 'error', error: err.message });
      }
    }

    const errs = session.errors();
    assert(suite, errs.page.length === 0, `no page errors (${errs.page.length})`);
  } finally {
    await session.cleanup();
  }

  await writeReport('mujoco_import', { results });
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
