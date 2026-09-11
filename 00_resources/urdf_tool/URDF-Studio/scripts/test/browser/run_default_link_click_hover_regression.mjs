#!/usr/bin/env node

import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { setTimeout as delay } from 'node:timers/promises';

import puppeteer from 'puppeteer';

const DEFAULT_SITE_URL = 'http://127.0.0.1:4173/?regressionDebug=1';
const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/default_link_click_hover_results.json');
const DEFAULT_SCREENSHOT_PATH = path.resolve(
  'tmp/regression/default_link_click_hover_regression.png',
);

function fail(message) {
  throw new Error(message);
}

function parseInteger(value, flagName) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    fail(`Invalid value for ${flagName}: ${value}`);
  }
  return parsed;
}

function parseArgs(argv) {
  const options = {
    siteUrl: DEFAULT_SITE_URL,
    timeoutMs: DEFAULT_TIMEOUT_MS,
    outputPath: DEFAULT_OUTPUT_PATH,
    screenshotPath: DEFAULT_SCREENSHOT_PATH,
    headed: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    const nextValue = () => {
      const value = argv[index + 1];
      if (value == null) {
        fail(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--site-url':
        options.siteUrl = nextValue();
        break;
      case '--timeout-ms':
        options.timeoutMs = parseInteger(nextValue(), '--timeout-ms');
        break;
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--screenshot':
        options.screenshotPath = path.resolve(nextValue());
        break;
      case '--headed':
        options.headed = true;
        break;
      case '--help':
      case '-h':
        console.log(`Usage:
  node scripts/test/browser/run_default_link_click_hover_regression.mjs [options]

Options:
  --site-url <url>      Dev server URL. Default: ${DEFAULT_SITE_URL}
  --timeout-ms <ms>     Timeout for page operations. Default: ${DEFAULT_TIMEOUT_MS}
  --output <path>       Result JSON path. Default: ${DEFAULT_OUTPUT_PATH}
  --screenshot <path>   Screenshot path. Default: ${DEFAULT_SCREENSHOT_PATH}
  --headed              Launch a headed browser.
`);
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

async function retryPageAction(action, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      return await action();
    } catch (error) {
      lastError = error;
      await delay(150);
    }
  }

  throw new Error(`Timed out while ${label}: ${lastError?.message ?? 'unknown error'}`);
}

async function writeJsonAtomic(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await fs.rename(tempPath, filePath);
}

function summarizeSelection(selection) {
  if (!selection?.type || !selection?.id) {
    return {
      type: null,
      id: null,
      subType: null,
      objectIndex: null,
      highlightObjectId: null,
    };
  }

  return {
    type: selection.type,
    id: selection.id,
    subType: selection.subType ?? null,
    objectIndex: selection.objectIndex ?? null,
    highlightObjectId: selection.highlightObjectId ?? null,
  };
}

function matchesBaseLinkVisual(selection) {
  return (
    selection?.type === 'link' &&
    selection.id === 'base_link' &&
    selection.subType === 'visual' &&
    (selection.objectIndex ?? 0) === 0
  );
}

async function waitForDebugApi(page, timeoutMs) {
  await retryPageAction(
    () =>
      page.waitForFunction(
        () => {
          return Boolean(
            window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot &&
            window.__URDF_STUDIO_DEBUG__?.getProjectedInteractionTargets,
          );
        },
        { timeout: Math.min(timeoutMs, 5_000) },
      ),
    timeoutMs,
    'waiting for regression debug API',
  );
}

async function setViewerToolMode(page, toolMode, timeoutMs) {
  await retryPageAction(
    () =>
      page.evaluate(
        (nextToolMode) => window.__URDF_STUDIO_DEBUG__?.setViewerToolMode?.(nextToolMode) ?? null,
        toolMode,
      ),
    timeoutMs,
    `setting viewer tool mode to ${toolMode}`,
  );

  await retryPageAction(
    () =>
      page.waitForFunction(
        (expectedToolMode) =>
          window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.viewer?.toolMode ===
          expectedToolMode,
        { timeout: Math.min(timeoutMs, 5_000) },
        toolMode,
      ),
    timeoutMs,
    `waiting for viewer tool mode ${toolMode}`,
  );
}

async function getBaseLinkVisualTarget(page, timeoutMs) {
  await retryPageAction(
    () =>
      page.waitForFunction(
        () => {
          const targets = window.__URDF_STUDIO_DEBUG__?.getProjectedInteractionTargets?.() ?? [];
          return targets.some(
            (entry) =>
              entry?.type === 'link' &&
              entry?.id === 'base_link' &&
              entry?.subType === 'visual' &&
              Number.isFinite(entry?.clientX) &&
              Number.isFinite(entry?.clientY),
          );
        },
        { timeout: Math.min(timeoutMs, 5_000) },
      ),
    timeoutMs,
    'waiting for base_link visual target',
  );

  return await retryPageAction(
    () =>
      page.evaluate(() => {
        const targets = window.__URDF_STUDIO_DEBUG__?.getProjectedInteractionTargets?.() ?? [];
        return (
          targets.find(
            (entry) =>
              entry?.type === 'link' && entry?.id === 'base_link' && entry?.subType === 'visual',
          ) ?? null
        );
      }),
    timeoutMs,
    'reading base_link visual target',
  );
}

async function readInteractionSnapshot(page, timeoutMs) {
  return await retryPageAction(
    () =>
      page.evaluate(() => {
        const interaction =
          window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.interaction ?? null;
        return {
          selection: interaction?.selection ?? null,
          hoveredSelection: interaction?.hoveredSelection ?? null,
        };
      }),
    timeoutMs,
    'reading interaction snapshot',
  );
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const browser = await puppeteer.launch({
    headless: options.headed ? false : true,
    defaultViewport: {
      width: 1600,
      height: 1100,
      deviceScaleFactor: 1,
    },
  });

  let result = null;

  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(options.timeoutMs);

    await page.goto(options.siteUrl, {
      waitUntil: 'domcontentloaded',
      timeout: options.timeoutMs,
    });

    await waitForDebugApi(page, options.timeoutMs);
    await setViewerToolMode(page, 'select', options.timeoutMs);

    const target = await getBaseLinkVisualTarget(page, options.timeoutMs);
    if (!target) {
      fail('Could not resolve a projected base_link visual hover target.');
    }

    await page.mouse.move(target.clientX, target.clientY);
    await delay(180);

    const beforeClick = await readInteractionSnapshot(page, options.timeoutMs);

    await page.mouse.down();
    await delay(40);
    const duringPointerDown = await readInteractionSnapshot(page, options.timeoutMs);
    await page.mouse.up();

    const immediateAfterClick = await readInteractionSnapshot(page, options.timeoutMs);
    await delay(140);
    const afterSettleWindow = await readInteractionSnapshot(page, options.timeoutMs);
    await delay(260);
    const afterExtendedIdle = await readInteractionSnapshot(page, options.timeoutMs);

    await fs.mkdir(path.dirname(options.screenshotPath), { recursive: true });
    await page.screenshot({
      path: options.screenshotPath,
      type: 'png',
    });

    result = {
      siteUrl: options.siteUrl,
      target: {
        id: target.id,
        subType: target.subType,
        objectIndex: target.objectIndex ?? null,
        clientX: target.clientX,
        clientY: target.clientY,
      },
      snapshots: {
        beforeClick: {
          selection: summarizeSelection(beforeClick.selection),
          hoveredSelection: summarizeSelection(beforeClick.hoveredSelection),
        },
        duringPointerDown: {
          selection: summarizeSelection(duringPointerDown.selection),
          hoveredSelection: summarizeSelection(duringPointerDown.hoveredSelection),
        },
        immediateAfterClick: {
          selection: summarizeSelection(immediateAfterClick.selection),
          hoveredSelection: summarizeSelection(immediateAfterClick.hoveredSelection),
        },
        afterSettleWindow: {
          selection: summarizeSelection(afterSettleWindow.selection),
          hoveredSelection: summarizeSelection(afterSettleWindow.hoveredSelection),
        },
        afterExtendedIdle: {
          selection: summarizeSelection(afterExtendedIdle.selection),
          hoveredSelection: summarizeSelection(afterExtendedIdle.hoveredSelection),
        },
      },
      screenshotPath: options.screenshotPath,
      generatedAt: new Date().toISOString(),
    };

    await writeJsonAtomic(options.outputPath, result);

    assert.equal(
      matchesBaseLinkVisual(beforeClick.hoveredSelection),
      true,
      'expected the initial mouse move to hover the default base_link visual',
    );
    assert.equal(
      matchesBaseLinkVisual(immediateAfterClick.selection),
      true,
      'expected the click to select the default base_link visual',
    );
    assert.equal(
      matchesBaseLinkVisual(immediateAfterClick.hoveredSelection),
      true,
      'expected hover to remain on base_link immediately after the click',
    );
    assert.equal(
      matchesBaseLinkVisual(afterSettleWindow.hoveredSelection),
      true,
      'expected hover to remain on base_link after the short settle window',
    );
    assert.equal(
      matchesBaseLinkVisual(afterExtendedIdle.hoveredSelection),
      true,
      'expected hover to remain on base_link after the extended idle check',
    );
  } finally {
    await browser.close();
  }
}

await main();
