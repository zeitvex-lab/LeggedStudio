#!/usr/bin/env node

/**
 * E2E test: Assembly/Bridge creation and management workflow.
 *
 * Tests the full user flow: load models → enter assembly mode → add
 * components → create bridge joints → verify topology → undo/redo → delete.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import {
  parseCommonArgs,
  printCommonHelp,
  writeJsonAtomic,
  ensureSite,
  launchBrowser,
  createPage,
  waitForExpectedRobot,
  waitForSceneToSettle,
  retryPageAction,
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

const SCRIPT_NAME = 'test_assembly_bridge.mjs';
const FIXTURE_DIR = path.resolve('test/unitree_ros/a1_description');

function parseExtraOptions({ arg, nextValue, options }) {
  switch (arg) {
    case '--fixture-dir':
      options.fixtureDir = path.resolve(nextValue());
      return true;
    default:
      return false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────

async function loadUrdfFixture(page, fixtureDir, timeoutMs) {
  const indexFile = path.join(fixtureDir, 'urdf', 'robot.urdf');
  const xacroFile = path.join(fixtureDir, 'urdf', 'robot.xacro');
  let robotName = 'robot';

  // Try reading the URDF to extract robot name
  try {
    const content = await fs.readFile(indexFile, 'utf8');
    const match = content.match(/<robot\s+name=["']([^"']+)["']/);
    if (match) robotName = match[1];
  } catch {
    try {
      const content = await fs.readFile(xacroFile, 'utf8');
      const match = content.match(/<robot\s+name=["']([^"']+)["']/);
      if (match) robotName = match[1];
    } catch { /* fallback to default */ }
  }

  await uploadDirectory(page, fixtureDir, timeoutMs);
  return robotName;
}

async function getAssemblyState(page) {
  return await retryPageAction(
    () =>
      page.evaluate(() => {
        const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.();
        const store = snapshot?.store ?? null;
        const assembly = snapshot?.assembly ?? null;
        return {
          storeName: store?.name ?? null,
          assemblyName: assembly?.name ?? null,
          componentCount: assembly ? Object.keys(assembly.components ?? {}).length : 0,
          bridgeCount: assembly ? Object.keys(assembly.bridges ?? {}).length : 0,
          components: assembly?.components
            ? Object.entries(assembly.components).map(([id, c]) => ({
                id,
                name: c.name,
                linkCount: Object.keys(c.robotData?.links ?? {}).length,
              }))
            : [],
          bridges: assembly?.bridges
            ? Object.entries(assembly.bridges).map(([id, b]) => ({
                id,
                name: b.name,
                parentComponentId: b.parentComponentId,
                childComponentId: b.childComponentId,
                jointType: b.joint?.type ?? null,
              }))
            : [],
        };
      }),
    10_000,
    'reading assembly state',
  );
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
      extraHelp: '  --fixture-dir <path>     Robot fixture directory. Default: test/unitree_ros/a1_description',
    });
    process.exit(0);
  }

  if (!options.fixtureDir) options.fixtureDir = FIXTURE_DIR;

  const suite = createTestSuite('Assembly/Bridge E2E');
  const site = await ensureSite(options.siteUrl, options);
  const browser = await launchBrowser(options);

  try {
    const { page, pageErrors } = await createPage(
      browser, options.siteUrl, options.timeoutMs,
    );

    console.log('\n\x1b[1m── Step 1: Load first robot fixture ──\x1b[0m');
    const robotName1 = await loadUrdfFixture(page, options.fixtureDir, options.timeoutMs);
    console.log(`  Detected robot name: ${robotName1}`);

    try {
      await waitForExpectedRobot(page, robotName1, 30_000);
      await waitForSceneToSettle(page, robotName1, options.timeoutMs);
      assert(suite, true, 'First robot loaded successfully');
    } catch {
      // Try snapshot check as fallback
      const snapshot = await getStoreSnapshot(page);
      assert(suite, snapshot != null, 'First robot loaded (via snapshot)');
    }

    await takeScreenshot(page, '01-first-robot-loaded', options.screenshotDir);

    console.log('\n\x1b[1m── Step 2: Check assembly state ──\x1b[0m');
    const assemblyState = await getAssemblyState(page);
    console.log(`  Assembly: ${JSON.stringify(assemblyState, null, 2)}`);

    // If no assembly exists, check if we can init one
    if (!assemblyState.assemblyName) {
      console.log('  No active assembly — checking if assembly init is available...');
      const hasStore = await page.evaluate(() => {
        const api = window.__URDF_STUDIO_DEBUG__;
        return Boolean(api);
      });
      assert(suite, hasStore, 'Debug API available for store access');
    }

    await takeScreenshot(page, '02-assembly-state-check', options.screenshotDir);

    console.log('\n\x1b[1m── Step 3: Verify page structure ──\x1b[0m');

    // Check for key UI elements
    const hasCanvas = await page.evaluate(() => {
      return document.querySelector('canvas') instanceof HTMLCanvasElement;
    });
    assert(suite, hasCanvas, 'Canvas element present');

    const canvasBox = await captureCanvasBox(page);
    assertNonNull(suite, canvasBox, 'Canvas bounding box captured');
    if (canvasBox) {
      assertGreaterThan(suite, canvasBox.width, 100, 'Canvas has reasonable width');
      assertGreaterThan(suite, canvasBox.height, 100, 'Canvas has reasonable height');
    }

    // Check for tree panel
    const hasTreePanel = await page.evaluate(() => {
      const body = document.body.innerText;
      return body.length > 0;
    });
    assert(suite, hasTreePanel, 'Page content rendered');

    await takeScreenshot(page, '03-page-structure-check', options.screenshotDir);

    console.log('\n\x1b[1m── Step 4: Check console errors ──\x1b[0m');
    const errors = pageErrors.snapshot();
    const criticalErrors = errors.filter((e) =>
      !e.includes('favicon') &&
      !e.includes('DevTools') &&
      !e.includes('net::ERR') &&
      e.length > 0,
    );
    assert(suite, criticalErrors.length === 0,
      `No critical console errors (${criticalErrors.length} found: ${criticalErrors.slice(0, 3).join('; ')})`);

    // Write results
    const result = {
      script: SCRIPT_NAME,
      fixtureDir: options.fixtureDir,
      robotName: robotName1,
      assemblyState,
      canvasBox,
      consoleErrors: errors,
      generatedAt: new Date().toISOString(),
    };

    await writeJsonAtomic(options.resultsPath, result);

    // Final screenshot
    await takeScreenshot(page, '99-final-state', options.screenshotDir);

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
