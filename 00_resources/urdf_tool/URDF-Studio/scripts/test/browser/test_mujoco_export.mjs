#!/usr/bin/env node

/**
 * MuJoCo Export browser regression test.
 *
 * Covers: MJCF import state, export dialog MJCF availability, real browser
 * download capture, and exported MJCF XML validation.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import JSZip from 'jszip';
import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

const MODEL = { dir: 'franka_emika_panda', file: 'panda.xml' };
const IMPORT_TIMEOUT_MS = 120_000;

async function prepareDownloadCapture(page) {
  const downloadDir = path.resolve(`tmp/regression/mujoco_export_download_${process.pid}_${Date.now()}`);
  await fs.mkdir(downloadDir, { recursive: true });
  const client = await page.target().createCDPSession();
  await client.send('Page.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: downloadDir,
  });
  return downloadDir;
}

async function openExportDialog(page) {
  const fileMenuOpened = await page.evaluate(() => {
    const buttons = [...document.querySelectorAll('button')];
    const button = buttons.find((candidate) => {
      const label = `${candidate.textContent ?? ''} ${candidate.getAttribute('aria-label') ?? ''} ${candidate.title ?? ''}`;
      return /\b(file|文件)\b/i.test(label);
    });
    button?.click();
    return Boolean(button);
  });
  if (!fileMenuOpened) return { fileMenuOpened, exportClicked: false, options: [] };
  await delay(250);

  const exportClicked = await page.evaluate(() => {
    const candidates = [...document.querySelectorAll('[role="menu"] button, [role="menuitem"], button')];
    const button = candidates.find((candidate) => /^(export|导出)$/i.test(candidate.textContent?.trim() ?? ''));
    button?.click();
    return Boolean(button);
  });
  if (!exportClicked) return { fileMenuOpened, exportClicked, options: [] };

  await page.waitForSelector('[data-export-format-picker]', { timeout: 45_000 });
  const options = await page.evaluate(() =>
    [...document.querySelectorAll('[data-export-format-picker] button')]
      .map((button) => ({
        text: button.textContent?.trim() ?? '',
        selected: button.getAttribute('aria-pressed') === 'true' || button.dataset?.selected === 'true',
      }))
      .filter((option) => option.text),
  );
  return { fileMenuOpened, exportClicked, options };
}

async function clickPrimaryExport(page) {
  return page.evaluate(() => {
    const buttons = [...document.querySelectorAll('button')];
    const button = buttons.reverse().find((candidate) => {
      if (candidate.disabled) return false;
      const label = candidate.textContent?.trim() ?? '';
      const isFormatPicker = Boolean(candidate.closest('[data-export-format-picker]'));
      return !isFormatPicker && /(export|导出)/i.test(label);
    }) ?? buttons.reverse().find((candidate) =>
      !candidate.disabled && /bg-system-blue/.test(candidate.getAttribute('class') ?? ''));
    button?.click();
    return Boolean(button);
  });
}

async function waitForDownloadedZip(downloadDir, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const entries = await fs.readdir(downloadDir).catch(() => []);
    const zipName = entries.find((entry) => entry.endsWith('.zip') && !entry.endsWith('.crdownload'));
    if (zipName) {
      const zipPath = path.join(downloadDir, zipName);
      const stat = await fs.stat(zipPath);
      if (stat.size > 0) return zipPath;
    }
    await delay(250);
  }
  throw new Error(`Timed out waiting for exported zip in ${downloadDir}`);
}

async function readExportedMjcf(zipPath) {
  const zip = await JSZip.loadAsync(await fs.readFile(zipPath));
  const entries = Object.values(zip.files);
  const xmlEntry = entries.find((entry) => !entry.dir && entry.name.endsWith('.xml'));
  if (!xmlEntry) {
    return { zipPath, entryNames: entries.map((entry) => entry.name), error: 'no exported XML entry' };
  }
  const xml = await xmlEntry.async('string');
  return {
    zipPath,
    fileName: path.basename(zipPath),
    entryNames: entries.map((entry) => entry.name),
    xmlEntry: xmlEntry.name,
    xml,
    bodyCount: xml.match(/<body\b/g)?.length ?? 0,
    geomCount: xml.match(/<geom\b/g)?.length ?? 0,
    actuatorCount: xml.match(/<(position|velocity|motor)\b/g)?.length ?? 0,
  };
}

async function main() {
  const suite = createTestSuite('MuJoCo Export');
  let session = null;
  const report = { model: MODEL, steps: [] };

  try {
    session = await createSession();
    const { page } = session;

    await importModel(page, MODEL.dir, MODEL.file, IMPORT_TIMEOUT_MS);
    await waitForReady(page);
    const topo = await getTopology(page);
    report.topology = { name: topo.name, links: topo.linkCount, joints: topo.jointCount };
    assertEqual(suite, topo.name, 'panda', 'Panda MJCF model name');
    assertGreaterThan(suite, topo.linkCount, 5, 'Panda MJCF links loaded');
    assertGreaterThan(suite, topo.jointCount, 5, 'Panda MJCF joints loaded');
    assert(suite, topo.links.some((link) => link.name === 'link0'), 'Panda link0 present');
    assert(suite, topo.joints.some((joint) => joint.name === 'joint1'), 'Panda joint1 present');

    const exportDialog = await openExportDialog(page);
    report.exportDialog = exportDialog;
    assert(suite, exportDialog.fileMenuOpened, 'file menu opened');
    assert(suite, exportDialog.exportClicked, 'export dialog opened');
    assertGreaterThan(suite, exportDialog.options.length, 0, 'export format options visible');
    assert(suite, exportDialog.options.some((option) => /MJCF/i.test(option.text)), 'export dialog exposes MJCF option');

    const downloadDir = await prepareDownloadCapture(page);
    const clickedExport = await clickPrimaryExport(page);
    assert(suite, clickedExport, 'primary export button clicked');
    const zipPath = await waitForDownloadedZip(downloadDir);
    const exported = await readExportedMjcf(zipPath);
    report.exported = {
      fileName: exported.fileName,
      zipPath: exported.zipPath,
      xmlEntry: exported.xmlEntry,
      entryCount: exported.entryNames?.length ?? 0,
      bodyCount: exported.bodyCount,
      geomCount: exported.geomCount,
      actuatorCount: exported.actuatorCount,
      xmlPreview: exported.xml?.slice(0, 500) ?? null,
      error: exported.error ?? null,
    };

    assert(suite, !exported.error, exported.error ?? 'real MJCF zip contains XML');
    assert(suite, /_mjcf\.zip$/i.test(exported.fileName), 'downloaded file is MJCF zip');
    assert(suite, exported.xml.includes('<mujoco'), 'exported XML has mujoco root');
    assert(suite, exported.xml.includes('<worldbody>'), 'exported XML has worldbody');
    assert(suite, exported.xml.includes('link0'), 'exported XML includes Panda body name');
    assert(suite, exported.xml.includes('joint1'), 'exported XML includes Panda joint');
    assertGreaterThan(suite, exported.bodyCount, Math.floor(topo.linkCount * 0.8), 'exported XML body count tracks topology');
    assertGreaterThan(suite, exported.geomCount, 0, 'exported XML contains geometry records');
    assertGreaterThan(suite, exported.entryNames.length, 1, 'exported zip includes XML plus assets');

    const after = await getTopology(page);
    assertEqual(suite, after.linkCount, topo.linkCount, 'export flow preserves link count');
    assertEqual(suite, after.jointCount, topo.jointCount, 'export flow preserves joint count');

    const errs = session.errors();
    report.errors = errs;
    assert(suite, errs.page.length === 0, 'no page errors');
  } catch (error) {
    report.error = error instanceof Error ? (error.stack ?? error.message) : String(error);
    assert(suite, false, `unexpected error: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    if (session) await session.cleanup();
  }

  await writeReport('mujoco_export', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
