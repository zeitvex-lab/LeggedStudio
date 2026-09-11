#!/usr/bin/env node

/**
 * Multi-format import matrix browser regression test (smoke).
 *
 * Imports one fixture per supported format (MJCF, URDF, SDF, USD, USDA)
 * and verifies each loads correctly.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  waitForReady, getTopology, getRuntimeTransforms, writeReport, printSummary,
} from './helpers/base-helpers.mjs';

import { importModel as importUrdf } from './helpers/urdf-helpers.mjs';
import { importModel as importMjcf } from './helpers/mjcf-helpers.mjs';
import { importModel as importSdf } from './helpers/sdf-helpers.mjs';
import { importUnitreeModel } from './helpers/usd-helpers.mjs';

const FORMATS = [
  { label: 'MJCF', format: 'mjcf', dir: 'unitree_go2', file: 'go2.xml' },
  { label: 'URDF', format: 'urdf', dir: 'a1_description', file: 'a1.urdf' },
  { label: 'SDF',  format: 'sdf',  dir: 'demo_joint_friction', file: 'model.sdf' },
];

const USD_MODELS = [
  { label: 'USD', key: 'Go2' },
];

async function main() {
  const suite = createTestSuite('Multi-Format Import Matrix');
  const session = await createSession();
  const results = [];

  try {
    // ── Directory-upload formats ──
    for (const { label, format, dir, file } of FORMATS) {
      console.log(`\n── ${label}: ${dir}/${file} ──`);
      try {
        if (format === 'mjcf') {
          await importMjcf(session.page, dir, file);
        } else if (format === 'urdf') {
          await importUrdf(session.page, dir, file);
        } else if (format === 'sdf') {
          await importSdf(session.page, dir, file);
        }
        await waitForReady(session.page);
        const topo = await getTopology(session.page);

        assertGreaterThan(suite, topo.linkCount, 0, `${label}: links > 0`);
        assertGreaterThan(suite, topo.jointCount, 0, `${label}: joints > 0`);

        results.push({ format: label, status: 'ok', links: topo.linkCount, joints: topo.jointCount });
      } catch (err) {
        assert(suite, false, `${label}: load succeeded — ${err.message}`);
        results.push({ format: label, status: 'error', error: err.message });
      }
    }

    // ── USD models (seed-and-load) ──
    for (const { label, key } of USD_MODELS) {
      console.log(`\n── ${label}: ${key} ──`);
      try {
        await session.page.reload({ waitUntil: 'domcontentloaded' });
        await session.page.waitForFunction(
          () => Boolean(window.__URDF_STUDIO_DEBUG__),
          { timeout: 30_000 },
        );
        await session.page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false));

        await importUnitreeModel(session.page, key);
        await waitForReady(session.page, 120_000);
        const topo = await getTopology(session.page);
        const runtimeTransforms = await getRuntimeTransforms(session.page);
        const usdState = await session.page.evaluate(() => {
          const api = window.__URDF_STUDIO_DEBUG__;
          const snap = api?.getRegressionSnapshot?.();
          const load = api?.getDocumentLoadState?.();
          return { selectedFile: snap?.selectedFile ?? null, loadState: load ?? null };
        });

        assertGreaterThan(suite, topo.linkCount, 0, `${label}: links > 0`);
        assertGreaterThan(suite, runtimeTransforms.length, 0, `${label}: runtime transforms present`);
        assert(suite, usdState.selectedFile?.format === 'usd', `${label}: selected file is USD`);
        assert(suite, usdState.loadState?.format === 'usd', `${label}: load state is USD`);
        assertEqual(suite, topo.jointCount, 0, `${label}: Go2 USD hydrates without URDF joints`);

        results.push({
          format: label,
          status: 'ok',
          links: topo.linkCount,
          joints: topo.jointCount,
          runtimeTransforms: runtimeTransforms.length,
          selectedFile: usdState.selectedFile?.name ?? null,
        });
      } catch (err) {
        assert(suite, false, `${label}: load succeeded — ${err.message}`);
        results.push({ format: label, status: 'error', error: err.message });
      }
    }

    const errs = session.errors();
    assert(suite, errs.page.length === 0, `no page errors (${errs.page.length})`);
  } finally {
    await session.cleanup();
  }

  await writeReport('multi_format_import', { results });
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
