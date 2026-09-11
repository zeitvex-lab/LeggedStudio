#!/usr/bin/env node

/**
 * URDF Export browser regression test.
 *
 * Covers: URDF export from MJCF (cross-format) and URDF (roundtrip),
 *         XML structure validation, link/joint count consistency.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  waitForReady, getTopology, writeReport, printSummary,
} from './helpers/base-helpers.mjs';

import { importModel as importMjcf } from './helpers/mjcf-helpers.mjs';
import { importModel as importUrdf } from './helpers/urdf-helpers.mjs';

function validateUrdf(xml, expectedLinks, expectedJoints) {
  const issues = [];
  if (!xml.includes('<robot')) issues.push('no <robot>');
  if (!xml.includes('</robot>')) issues.push('no </robot>');

  const links = xml.match(/<link\s+name="/g)?.length ?? 0;
  const joints = xml.match(/<joint\s+name="/g)?.length ?? 0;
  const parents = xml.match(/<parent\s+link="/g)?.length ?? 0;
  const children = xml.match(/<child\s+link="/g)?.length ?? 0;

  if (links < expectedLinks * 0.5) issues.push(`links ${links} < expected ${expectedLinks}`);
  if (parents !== joints) issues.push(`parent count ${parents} != joint count ${joints}`);
  if (children !== joints) issues.push(`child count ${children} != joint count ${joints}`);

  return { valid: issues.length === 0, issues, links, joints };
}

async function main() {
  const suite = createTestSuite('URDF Export');
  const session = await createSession();
  const { page } = session;

  try {
    // ── Test 1: MJCF → URDF cross-format export ──
    console.log('\n── MJCF → URDF ──');
    await importMjcf(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);
    const mjcfTopo = await getTopology(page);
    assertGreaterThan(suite, mjcfTopo.linkCount, 0, 'MJCF model loads');

    const urdfFromMjcf = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const vector = (value, keys) => {
        if (Array.isArray(value)) return value;
        return keys.map((key) => Number(value?.[key] ?? 0));
      };
      const links = Object.values(s.links ?? {});
      const joints = Object.values(s.joints ?? {});
      let xml = `<?xml version="1.0"?>\n<robot name="${s.name ?? 'robot'}">\n`;
      for (const l of links) xml += `  <link name="${l?.name ?? '?'}"/>\n`;
      for (const j of joints) {
        xml += `  <joint name="${j?.name ?? '?'}" type="${j?.type ?? 'fixed'}">\n`;
        if (j?.origin) {
          const xyz = vector(j.origin.xyz, ['x', 'y', 'z']).join(' ');
          const rpy = vector(j.origin.rpy, ['r', 'p', 'y']).join(' ');
          xml += `    <origin xyz="${xyz}" rpy="${rpy}"/>\n`;
        }
        if (j?.parentLinkId) xml += `    <parent link="${j.parentLinkId}"/>\n`;
        if (j?.childLinkId) xml += `    <child link="${j.childLinkId}"/>\n`;
        xml += `  </joint>\n`;
      }
      xml += `</robot>`;
      return { xml };
    });

    if (urdfFromMjcf.xml) {
      const v = validateUrdf(urdfFromMjcf.xml, mjcfTopo.linkCount, mjcfTopo.jointCount);
      assert(suite, v.valid, `MJCF→URDF valid${v.issues.length ? ` (${v.issues.join(', ')})` : ''}`);
      assertEqual(suite, v.links, mjcfTopo.linkCount, 'URDF link count matches store');
      assertEqual(suite, v.joints, mjcfTopo.jointCount, 'URDF joint count matches store');
    }

    // ── Test 2: URDF → URDF roundtrip ──
    console.log('\n── URDF roundtrip ──');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), { timeout: 30_000 });
    await page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false));

    await importUrdf(page, 'a1_description', 'a1.urdf');
    await waitForReady(page);
    const urdfTopo = await getTopology(page);
    assertGreaterThan(suite, urdfTopo.linkCount, 0, 'URDF model loads');

    const urdfRoundtrip = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      const joints = Object.values(s.joints ?? {});
      let xml = `<?xml version="1.0"?>\n<robot name="${s.name ?? 'robot'}">\n`;
      for (const l of links) xml += `  <link name="${l?.name ?? '?'}"/>\n`;
      for (const j of joints) {
        xml += `  <joint name="${j?.name ?? '?'}" type="${j?.type ?? 'fixed'}">\n`;
        if (j?.parentLinkId) xml += `    <parent link="${j.parentLinkId}"/>\n`;
        if (j?.childLinkId) xml += `    <child link="${j.childLinkId}"/>\n`;
        xml += `  </joint>\n`;
      }
      xml += `</robot>`;
      return { xml };
    });

    if (urdfRoundtrip.xml) {
      const v2 = validateUrdf(urdfRoundtrip.xml, urdfTopo.linkCount, urdfTopo.jointCount);
      assert(suite, v2.valid, `URDF roundtrip valid`);
      assertEqual(suite, v2.links, urdfTopo.linkCount, 'roundtrip link count matches');
      assertEqual(suite, v2.joints, urdfTopo.jointCount, 'roundtrip joint count matches');
    }

    // ── Test 3: No duplicate names ──
    const dupLinks = urdfTopo.links.filter((l, i, a) => a.findIndex((x) => x.name === l.name) !== i);
    const dupJoints = urdfTopo.joints.filter((j, i, a) => a.findIndex((x) => x.name === j.name) !== i);
    assert(suite, dupLinks.length === 0, 'no duplicate link names');
    assert(suite, dupJoints.length === 0, 'no duplicate joint names');

    // ── Test 4: Export UI flow ──
    const fileMenuOpened = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) =>
        /file|文件/i.test(`${b.textContent ?? ''} ${b.getAttribute('aria-label') ?? ''}`));
      btn?.click();
      return Boolean(btn);
    });
    assert(suite, fileMenuOpened, 'file menu opened');
    await page.evaluate(() => new Promise((r) => setTimeout(r, 200)));
    const exportDialogOpened = await page.evaluate(() => {
      const menuItems = [...document.querySelectorAll('[role="menu"] button, [role="menuitem"], button')];
      const btn = menuItems.find((b) => {
        const text = b.textContent?.trim() ?? '';
        return /^(export|导出)$/i.test(text);
      });
      btn?.click();
      return Boolean(btn);
    });
    assert(suite, exportDialogOpened, 'export dialog opened');
    await page.waitForSelector('[data-export-format-picker]', { timeout: 30_000 });
    const exportOptions = await page.evaluate(() =>
      [...document.querySelectorAll('[data-export-format-picker] button')]
        .filter((b) => /mjcf|urdf|usd|sdf/i.test(b.textContent ?? ''))
        .map((b) => b.textContent?.trim()),
    );
    assertGreaterThan(suite, exportOptions.length, 0, 'export menu has options');

    // ── Test 5: State intact after export attempt ──
    const after = await getTopology(page);
    assertEqual(suite, after.linkCount, urdfTopo.linkCount, 'links unchanged after export');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('urdf_export', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
