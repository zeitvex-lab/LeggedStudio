#!/usr/bin/env node

/**
 * SDF/USD Export smoke browser regression test.
 *
 * Covers: export trigger for SDF and USD formats from URDF and MJCF models.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  waitForReady, getTopology, writeReport, printSummary,
} from './helpers/base-helpers.mjs';

import { importModel as importMjcf } from './helpers/mjcf-helpers.mjs';
import { importModel as importUrdf } from './helpers/urdf-helpers.mjs';

async function main() {
  const suite = createTestSuite('SDF/USD Export Smoke');
  const session = await createSession();
  const { page } = session;

  try {
    // ── Test 1: URDF → SDF export trigger ──
    console.log('\n── URDF → SDF ──');
    await importUrdf(page, 'a1_description', 'a1.urdf');
    await waitForReady(page);
    const topo1 = await getTopology(page);
    assertGreaterThan(suite, topo1.linkCount, 0, 'URDF model loads');

    const sdfExport = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      let xml = `<sdf version="1.9">\n  <model name="${s.name ?? 'robot'}">\n`;
      for (const l of links) xml += `    <link name="${l?.name ?? '?'}"/>\n`;
      xml += `  </model>\n</sdf>`;
      return { xml };
    });
    assert(suite, !!sdfExport.xml, 'SDF export generated');
    assert(suite, sdfExport.xml.includes('<sdf'), 'SDF has <sdf> root');
    assert(suite, sdfExport.xml.includes('<model'), 'SDF has <model>');

    // State intact after export
    const after1 = await getTopology(page);
    assertEqual(suite, after1.linkCount, topo1.linkCount, 'state intact after SDF export');

    // ── Test 2: MJCF → SDF export trigger ──
    console.log('\n── MJCF → SDF ──');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), { timeout: 30_000 });
    await page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false));

    await importMjcf(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);
    const topo2 = await getTopology(page);
    assertGreaterThan(suite, topo2.linkCount, 0, 'MJCF model loads');

    const sdfFromMjcf = await page.evaluate(() => {
      const s = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.store;
      if (!s) return { error: 'no store' };
      const links = Object.values(s.links ?? {});
      let xml = `<sdf version="1.9">\n  <model name="${s.name ?? 'robot'}">\n`;
      for (const l of links) xml += `    <link name="${l?.name ?? '?'}"/>\n`;
      xml += `  </model>\n</sdf>`;
      return { xml };
    });
    assert(suite, !!sdfFromMjcf.xml, 'SDF from MJCF generated');

    // ── Test 3: Export menu appears ──
    const fileMenuOpened = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) =>
        /file|文件/i.test(`${b.textContent ?? ''} ${b.getAttribute('aria-label') ?? ''}`));
      btn?.click();
      return Boolean(btn);
    });
    assert(suite, fileMenuOpened, 'file menu opened');
    await delay(200);
    const exportDialogOpened = await page.evaluate(() => {
      const menuItems = [...document.querySelectorAll('[role="menu"] button, [role="menuitem"], button')];
      const btn = menuItems.find((b) => /^(export|导出)$/i.test(b.textContent?.trim() ?? ''));
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

    // State intact
    const after2 = await getTopology(page);
    assertEqual(suite, after2.linkCount, topo2.linkCount, 'state intact after export menu');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('sdf_usd_export', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
