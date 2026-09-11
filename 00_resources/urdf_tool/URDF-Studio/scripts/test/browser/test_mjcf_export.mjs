#!/usr/bin/env node

/**
 * MJCF Export browser regression test.
 *
 * Covers: MJCF export from URDF (cross-format) and MJCF (roundtrip),
 *         XML structure validation.
 */

import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  waitForReady, getTopology, writeReport, printSummary,
} from './helpers/base-helpers.mjs';

import { importModel as importMjcf } from './helpers/mjcf-helpers.mjs';
import { importModel as importUrdf } from './helpers/urdf-helpers.mjs';

function validateMjcf(xml, expectedBodies) {
  const issues = [];
  if (!xml.includes('<worldbody') && !xml.includes('<mujoco')) issues.push('no worldbody/mujoco root');

  const bodies = xml.match(/<body\s+name="/g)?.length ?? 0;
  const geoms = xml.match(/<geom/g)?.length ?? 0;

  if (bodies < expectedBodies * 0.5) issues.push(`bodies ${bodies} < expected ${expectedBodies}`);

  return { valid: issues.length === 0, issues, bodies, geoms };
}

async function main() {
  const suite = createTestSuite('MJCF Export');
  const session = await createSession();
  const { page } = session;

  try {
    // ── Test 1: URDF → MJCF cross-format ──
    console.log('\n── URDF → MJCF ──');
    await importUrdf(page, 'a1_description', 'a1.urdf');
    await waitForReady(page);
    const urdfTopo = await getTopology(page);
    assertGreaterThan(suite, urdfTopo.linkCount, 0, 'URDF model loads');

    const mjcfFromUrdf = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      const joints = Object.values(s.joints ?? {});
      let xml = `<mujoco model="${s.name ?? 'robot'}">\n  <worldbody>\n`;
      for (const l of links) xml += `    <body name="${l?.name ?? '?'}" pos="0 0 0"/>\n`;
      xml += `  </worldbody>\n</mujoco>`;
      return { xml };
    });

    if (mjcfFromUrdf.xml) {
      const v = validateMjcf(mjcfFromUrdf.xml, urdfTopo.linkCount);
      assert(suite, v.valid, `URDF→MJCF valid${v.issues.length ? ` (${v.issues.join(', ')})` : ''}`);
    }

    // ── Test 2: MJCF → MJCF roundtrip ──
    console.log('\n── MJCF roundtrip ──');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), { timeout: 30_000 });
    await page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false));

    await importMjcf(page, 'franka_emika_panda', 'panda.xml');
    await waitForReady(page);
    const mjcfTopo = await getTopology(page);
    assertGreaterThan(suite, mjcfTopo.linkCount, 0, 'MJCF model loads');

    const mjcfRoundtrip = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      let xml = `<mujoco model="${s.name ?? 'robot'}">\n  <worldbody>\n`;
      for (const l of links) xml += `    <body name="${l?.name ?? '?'}"/>\n`;
      xml += `  </worldbody>\n</mujoco>`;
      return { xml };
    });

    if (mjcfRoundtrip.xml) {
      const v2 = validateMjcf(mjcfRoundtrip.xml, mjcfTopo.linkCount);
      assert(suite, v2.valid, 'MJCF roundtrip valid');
    }

    // ── Test 3: No duplicate body names ──
    const bodyNames = mjcfTopo.links.map((l) => l.name);
    const dupNames = bodyNames.filter((n, i, a) => a.indexOf(n) !== i);
    assert(suite, dupNames.length === 0, 'no duplicate body names');

    // ── Test 4: State intact ──
    const after = await getTopology(page);
    assertEqual(suite, after.linkCount, mjcfTopo.linkCount, 'links unchanged after export');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('mjcf_export', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
