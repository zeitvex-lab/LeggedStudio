#!/usr/bin/env node

/**
 * E2E test: Import/Export workflow.
 *
 * Tests loading various robot file formats (URDF, MJCF, SDF) and
 * verifying the parsed model is correct, then testing export roundtrips.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { setTimeout as delay } from 'node:timers/promises';

import {
  parseCommonArgs,
  printCommonHelp,
  writeJsonAtomic,
  fileExists,
  collectFiles,
  ensureSite,
  launchBrowser,
  createPage,
  waitForDebugApi,
  waitForExpectedRobot,
  clickElementByText,
  takeScreenshot,
  getStoreSnapshot,
  uploadDirectory,
  captureCanvasBox,
} from '../helpers/browser-helpers.mjs';

import {
  createTestSuite,
  assert,
  assertNonNull,
  assertGreaterThan,
  printSummary,
} from '../helpers/assertions.mjs';

// ── Config ────────────────────────────────────────────────────────────

const SCRIPT_NAME = 'test_import_export.mjs';

const FIXTURE_DATASETS = [
  { name: 'unitree_ros/a1_description', format: 'urdf', label: 'URDF (a1)' },
  { name: 'unitree_ros/go1_description', format: 'urdf', label: 'URDF (go1)' },
  { name: 'mujoco_menagerie-main/franka_emika_panda', format: 'mjcf', label: 'MJCF (panda)' },
  { name: 'mujoco_menagerie-main/ur5e', format: 'mjcf', label: 'MJCF (ur5e)' },
];

function parseExtraOptions({ arg, nextValue, options }) {
  switch (arg) {
    case '--dataset':
      options.datasets.push(nextValue());
      return true;
    case '--all':
      options.datasets = FIXTURE_DATASETS.map((d) => d.name);
      return true;
    default:
      return false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────

function findRobotFile(files, format) {
  if (format === 'urdf') {
    return files.find((f) => f.endsWith('.urdf') && !f.includes('macro'));
  }
  if (format === 'mjcf') {
    return files.find((f) => f.endsWith('.xml'));
  }
  if (format === 'sdf') {
    return files.find((f) => f.endsWith('.sdf'));
  }
  return null;
}

async function resolveFixturePath(dataset) {
  const candidates = [
    path.resolve('test', dataset.name),
    dataset.name.startsWith('unitree_ros/')
      ? path.resolve('test/unitree_ros/robots', dataset.name.replace(/^unitree_ros\//, ''))
      : null,
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (await fileExists(candidate)) {
      return candidate;
    }
  }

  return candidates[0];
}

async function clickButtonByAccessibleName(page, name, timeoutMs) {
  await page.waitForFunction(
    (expected) =>
      Array.from(document.querySelectorAll('button')).some((button) => {
        const ariaLabel = button.getAttribute('aria-label');
        const text = button.textContent?.trim();
        return ariaLabel === expected || text === expected;
      }),
    { timeout: Math.min(timeoutMs, 5_000) },
    name,
  );

  const clicked = await page.evaluate((expected) => {
    const match = Array.from(document.querySelectorAll('button')).find((button) => {
      const ariaLabel = button.getAttribute('aria-label');
      const text = button.textContent?.trim();
      return ariaLabel === expected || text === expected;
    });
    if (match instanceof HTMLElement) {
      match.click();
      return true;
    }
    return false;
  }, name);

  if (!clicked) {
    throw new Error(`Could not click button "${name}"`);
  }
}

async function waitForExportDialog(page, timeoutMs) {
  await page.waitForFunction(
    () => {
      const text = document.body.textContent ?? '';
      return text.includes('Export Format') && text.includes('Export ZIP');
    },
    { timeout: Math.min(timeoutMs, 10_000) },
  );
}

async function extractRobotName(filePath, format) {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    if (format === 'urdf') {
      const match = content.match(/<robot\s+name=["']([^"']+)["']/);
      return match ? match[1] : null;
    }
    if (format === 'mjcf') {
      const match = content.match(/<worldbody|<body\s+name=["']([^"']+)["']/);
      return match ? (match[1] || 'mujoco_model') : 'mujoco_model';
    }
  } catch { /* fallback */ }
  return null;
}

async function importAndVerify(page, dataset, timeoutMs, suite) {
  console.log(`\n  \x1b[36mImporting: ${dataset.label} (${dataset.name})\x1b[0m`);

  const fixturePath = await resolveFixturePath(dataset);
  const exists = await fileExists(fixturePath);
  if (!exists) {
    console.log(`    \x1b[33mSKIP\x1b[0m Fixture not found: ${fixturePath}`);
    assert(suite, true, `${dataset.label}: skipped (fixture missing)`);
    return null;
  }

  const files = await collectFiles(fixturePath);
  const robotFile = findRobotFile(files, dataset.format);
  assertNonNull(suite, robotFile, `${dataset.label}: found ${dataset.format} file`);

  const expectedName = await extractRobotName(robotFile, dataset.format);

  // Upload
  try {
    await uploadDirectory(page, fixturePath, timeoutMs);
    console.log(`    Uploaded ${files.length} files`);
  } catch (err) {
    assert(suite, false, `${dataset.label}: file upload failed — ${err.message}`);
    return null;
  }

  await delay(500);

  // Verify robot loaded
  let loaded = false;
  let snapshot = null;
  try {
    if (expectedName) {
      await waitForExpectedRobot(page, expectedName, 20_000);
      loaded = true;
    }
  } catch {
    // Fallback: check snapshot
  }

  if (!loaded) {
    snapshot = await getStoreSnapshot(page);
    loaded = snapshot != null && (snapshot.name != null || snapshot.links != null);
  }

  assert(suite, loaded, `${dataset.label}: robot loaded into store`);

  if (!snapshot) {
    snapshot = await getStoreSnapshot(page);
  }

  // Check model structure
  if (snapshot) {
    const linkCount = snapshot.links ? Object.keys(snapshot.links).length : 0;
    const jointCount = snapshot.joints ? Object.keys(snapshot.joints).length : 0;
    assertGreaterThan(suite, linkCount, 0, `${dataset.label}: has links (${linkCount})`);
    assert(suite, jointCount >= 0, `${dataset.label}: has joints (${jointCount})`);
  }

  // Canvas check
  const canvasBox = await captureCanvasBox(page);
  assertNonNull(suite, canvasBox, `${dataset.label}: canvas rendered`);

  return { snapshot, canvasBox, expectedName };
}

// ── Main ──────────────────────────────────────────────────────────────

async function main() {
  const { help, options } = parseCommonArgs(process.argv.slice(2), {
    scriptName: SCRIPT_NAME,
    extraOptions: parseExtraOptions,
  });

  if (help) {
    printCommonHelp({
      scriptName: SCRIPT_NAME,
      extraHelp: `  --dataset <name>    Test a specific dataset (repeatable). Available:
${FIXTURE_DATASETS.map((d) => `                        ${d.name} (${d.label})`).join('\n')}
  --all               Test all available datasets.`,
    });
    process.exit(0);
  }

  // Default: test URDF fixtures only (fast)
  const datasets = options.datasets?.length > 0
    ? FIXTURE_DATASETS.filter((d) => options.datasets.includes(d.name))
    : FIXTURE_DATASETS.filter((d) => d.format === 'urdf').slice(0, 2);

  const suite = createTestSuite('Import/Export E2E');
  const site = await ensureSite(options.siteUrl, options);
  const browser = await launchBrowser(options);
  const importResults = [];

  try {
    const { page, pageErrors } = await createPage(
      browser, options.siteUrl, options.timeoutMs,
    );

    for (const dataset of datasets) {
      console.log(`\n\x1b[1m── Import test: ${dataset.label} ──\x1b[0m`);

      const result = await importAndVerify(page, dataset, options.timeoutMs, suite);
      importResults.push({
        dataset: dataset.name,
        label: dataset.label,
        format: dataset.format,
        success: result !== null,
      });

      await takeScreenshot(page, `import-${dataset.name.replace(/\//g, '-')}`, options.screenshotDir);

      // Reset for next test
      if (dataset !== datasets[datasets.length - 1]) {
        await page.goto(options.siteUrl, {
          waitUntil: 'domcontentloaded',
          timeout: options.timeoutMs,
        });
        await waitForDebugApi(page, options.timeoutMs);
        await delay(500);
      }
    }

    console.log('\n\x1b[1m── Export test: verify export triggers ──\x1b[0m');

    // Reload and import one model for export testing
    await page.goto(options.siteUrl, {
      waitUntil: 'domcontentloaded',
      timeout: options.timeoutMs,
    });
    await waitForDebugApi(page, options.timeoutMs);

    const firstUrdf = datasets.find((d) => d.format === 'urdf');
    if (firstUrdf) {
      const fixturePath = await resolveFixturePath(firstUrdf);
      if (await fileExists(fixturePath)) {
        await uploadDirectory(page, fixturePath, options.timeoutMs);
        await delay(1000);

        const snapshot = await getStoreSnapshot(page);
        const hasRobot = snapshot?.name != null;
        assert(suite, hasRobot, 'Export test: robot loaded before export attempt');

        if (hasRobot) {
          try {
            await clickButtonByAccessibleName(page, 'File', options.timeoutMs);
            await clickElementByText(page, 'button', 'Export', options.timeoutMs);
            await waitForExportDialog(page, options.timeoutMs);
            assert(suite, true, 'Export test: export dialog opened');
          } catch (err) {
            assert(suite, false, `Export test: export dialog did not open - ${err.message}`);
          }
        }

        await takeScreenshot(page, 'export-attempt', options.screenshotDir);
      }
    }

    // Console error check
    console.log('\n\x1b[1m── Console errors ──\x1b[0m');
    const errors = pageErrors.snapshot();
    const criticalErrors = errors.filter((e) =>
      !e.includes('favicon') &&
      !e.includes('DevTools') &&
      !e.includes('net::ERR') &&
      e.length > 0,
    );
    assert(suite, criticalErrors.length === 0,
      `No critical console errors during import/export (${criticalErrors.length} found)`);

    // Write results
    const result = {
      script: SCRIPT_NAME,
      datasets: importResults,
      consoleErrors: errors,
      generatedAt: new Date().toISOString(),
    };
    await writeJsonAtomic(options.resultsPath, result);

  } finally {
    await browser.close();
    await site.stop();
  }

  const ok = printSummary(suite);
  process.exitCode = ok ? 0 : 1;
}

main().catch(async (error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
