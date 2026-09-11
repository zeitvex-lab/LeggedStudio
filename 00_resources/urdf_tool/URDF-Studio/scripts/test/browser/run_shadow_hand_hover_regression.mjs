#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import JSZip from 'jszip';
import puppeteer from 'puppeteer';

const DEFAULT_SITE_URL = 'http://127.0.0.1:4173';
const DEFAULT_FIXTURE_DIR = path.resolve('test/mujoco_menagerie-main/shadow_hand');
const DEFAULT_TMP_ROOT = path.resolve('tmp/regression');
const DEFAULT_ZIP_PATH = path.join(DEFAULT_TMP_ROOT, 'shadow_hand_fixture.zip');
const DEFAULT_OUTPUT_PATH = path.join(DEFAULT_TMP_ROOT, 'shadow_hand_hover_results.json');
const DEFAULT_SCREENSHOT_PATH = path.join(DEFAULT_TMP_ROOT, 'shadow_hand_hover_regression.png');
const DEFAULT_SITE_TIMEOUT_MS = 120_000;
const DEFAULT_OPERATION_TIMEOUT_MS = 30_000;
const DEFAULT_START_COMMAND = (host, port) =>
  `npm run dev -- --host ${host} --port ${port} --strictPort`;

const DEFAULT_VIEWPORT = {
  width: 1600,
  height: 1000,
  deviceScaleFactor: 1,
};

const FIXED_SAMPLE_POINTS = [{ name: 'empty_top_left', dx: 40, dy: 40, expected: null }];

const EXPECTED_FRONT_TARGETS = [
  'lh_forearm_geom_1:visual:',
  'lh_palm:visual:',
  'lh_lfmiddle:visual:',
];

const PROJECTED_TARGET_PROBE_OFFSETS = [
  [0, 0],
  [4, 0],
  [-4, 0],
  [0, 4],
  [0, -4],
];

function fail(message) {
  throw new Error(message);
}

function parseInteger(value, flagName) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    fail(`Invalid value for ${flagName}: ${value}`);
  }
  return parsed;
}

function parseArgs(argv) {
  const options = {
    siteUrl: DEFAULT_SITE_URL,
    fixtureDir: DEFAULT_FIXTURE_DIR,
    zipPath: DEFAULT_ZIP_PATH,
    outputPath: DEFAULT_OUTPUT_PATH,
    screenshotPath: DEFAULT_SCREENSHOT_PATH,
    siteTimeoutMs: DEFAULT_SITE_TIMEOUT_MS,
    timeoutMs: DEFAULT_OPERATION_TIMEOUT_MS,
    noStart: false,
    startCommand: null,
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
      case '--fixture-dir':
        options.fixtureDir = path.resolve(nextValue());
        break;
      case '--zip-path':
        options.zipPath = path.resolve(nextValue());
        break;
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--screenshot':
        options.screenshotPath = path.resolve(nextValue());
        break;
      case '--site-timeout-ms':
        options.siteTimeoutMs = parseInteger(nextValue(), '--site-timeout-ms');
        break;
      case '--timeout-ms':
        options.timeoutMs = parseInteger(nextValue(), '--timeout-ms');
        break;
      case '--start-command':
        options.startCommand = nextValue();
        break;
      case '--no-start':
        options.noStart = true;
        break;
      case '--headed':
        options.headed = true;
        break;
      case '--help':
      case '-h':
        printHelp();
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  const normalizedSiteUrl = new URL(options.siteUrl);
  normalizedSiteUrl.searchParams.set('regressionDebug', '1');
  options.siteUrl = normalizedSiteUrl.toString();
  return options;
}

function printHelp() {
  console.log(`Usage:
  node scripts/test/browser/run_shadow_hand_hover_regression.mjs [options]

Options:
  --site-url <url>          URDF Studio site URL. Default: ${DEFAULT_SITE_URL}
  --fixture-dir <path>      shadow_hand fixture directory. Default: ${DEFAULT_FIXTURE_DIR}
  --zip-path <path>         Temporary zip path. Default: ${DEFAULT_ZIP_PATH}
  --output <path>           Result JSON path. Default: ${DEFAULT_OUTPUT_PATH}
  --screenshot <path>       Screenshot path. Default: ${DEFAULT_SCREENSHOT_PATH}
  --site-timeout-ms <ms>    Site startup/connect timeout. Default: ${DEFAULT_SITE_TIMEOUT_MS}
  --timeout-ms <ms>         Browser operation timeout. Default: ${DEFAULT_OPERATION_TIMEOUT_MS}
  --start-command <cmd>     Override auto-start command when site is offline.
  --no-start                Fail instead of starting the site automatically.
  --headed                  Launch headed browser instead of headless.
  --help                    Show this help.
`);
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function collectFiles(rootDir) {
  const entries = [];

  async function visit(currentDir) {
    const dirents = await fs.readdir(currentDir, { withFileTypes: true });
    dirents.sort((left, right) => left.name.localeCompare(right.name));
    for (const dirent of dirents) {
      const fullPath = path.join(currentDir, dirent.name);
      if (dirent.isDirectory()) {
        await visit(fullPath);
        continue;
      }

      if (dirent.isFile()) {
        entries.push(fullPath);
      }
    }
  }

  await visit(rootDir);
  return entries;
}

async function zipFixtureDirectory(fixtureDir, zipPath) {
  if (!(await fileExists(fixtureDir))) {
    fail(`Fixture directory does not exist: ${fixtureDir}`);
  }

  await fs.mkdir(path.dirname(zipPath), { recursive: true });
  const zip = new JSZip();
  const files = await collectFiles(fixtureDir);

  if (files.length === 0) {
    fail(`Fixture directory is empty: ${fixtureDir}`);
  }

  for (const filePath of files) {
    const relativePath = path.relative(fixtureDir, filePath);
    const content = await fs.readFile(filePath);
    zip.file(relativePath, content);
  }

  const archive = await zip.generateAsync({
    type: 'nodebuffer',
    compression: 'DEFLATE',
    compressionOptions: { level: 9 },
  });

  await fs.writeFile(zipPath, archive);
  return {
    zipPath,
    fileCount: files.length,
    files: files.map((filePath) => path.relative(fixtureDir, filePath)),
  };
}

async function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      signal: controller.signal,
      redirect: 'follow',
      cache: 'no-store',
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function isSiteReachable(siteUrl, timeoutMs) {
  try {
    const response = await fetchWithTimeout(siteUrl, Math.min(timeoutMs, 10_000));
    return response.ok;
  } catch {
    return false;
  }
}

function createLogBuffer(limit = 200) {
  const lines = [];
  return {
    push(line) {
      if (typeof line !== 'string' || line.length === 0) {
        return;
      }
      lines.push(line);
      if (lines.length > limit) {
        lines.splice(0, lines.length - limit);
      }
    },
    toString() {
      return lines.join('\n');
    },
  };
}

function spawnSiteProcess(command, cwd) {
  const logs = createLogBuffer();
  const child = spawn(command, {
    cwd,
    shell: true,
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      BROWSER: 'none',
    },
  });

  child.stdout?.setEncoding('utf8');
  child.stderr?.setEncoding('utf8');
  child.stdout?.on('data', (chunk) => logs.push(String(chunk).trimEnd()));
  child.stderr?.on('data', (chunk) => logs.push(String(chunk).trimEnd()));

  return {
    child,
    logs,
    async stop() {
      if (child.exitCode != null || child.signalCode != null) {
        return;
      }

      try {
        process.kill(-child.pid, 'SIGTERM');
      } catch {
        return;
      }

      const deadline = Date.now() + 5_000;
      while (Date.now() < deadline) {
        if (child.exitCode != null || child.signalCode != null) {
          return;
        }
        await delay(100);
      }

      try {
        process.kill(-child.pid, 'SIGKILL');
      } catch {
        // ignore
      }
    },
  };
}

async function ensureSite(siteUrl, options) {
  if (await isSiteReachable(siteUrl, options.siteTimeoutMs)) {
    return {
      startedByScript: false,
      stop: async () => {},
    };
  }

  if (options.noStart) {
    fail(`Site is not reachable at ${siteUrl} and --no-start was set.`);
  }

  const parsedUrl = new URL(siteUrl);
  const host = parsedUrl.hostname;
  const port = parsedUrl.port || (parsedUrl.protocol === 'https:' ? '443' : '80');
  const command = options.startCommand ?? DEFAULT_START_COMMAND(host, port);
  const siteProcess = spawnSiteProcess(command, process.cwd());
  const deadline = Date.now() + options.siteTimeoutMs;

  try {
    while (Date.now() < deadline) {
      if (await isSiteReachable(siteUrl, 5_000)) {
        return {
          startedByScript: true,
          stop: siteProcess.stop,
        };
      }

      if (siteProcess.child.exitCode != null) {
        fail(
          `Site start command exited early: ${command}\n` +
            `Last logs:\n${siteProcess.logs.toString() || '(no logs captured)'}`,
        );
      }

      await delay(500);
    }

    fail(
      `Timed out waiting for site ${siteUrl} after starting: ${command}\n` +
        `Last logs:\n${siteProcess.logs.toString() || '(no logs captured)'}`,
    );
  } catch (error) {
    await siteProcess.stop();
    throw error;
  }
}

async function launchBrowser(options) {
  return await puppeteer.launch({
    headless: options.headed ? false : true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: DEFAULT_VIEWPORT,
  });
}

function ringBuffer(limit = 100) {
  const values = [];
  return {
    push(value) {
      values.push(value);
      if (values.length > limit) {
        values.splice(0, values.length - limit);
      }
    },
    snapshot() {
      return [...values];
    },
  };
}

function isRetryableExecutionError(error) {
  const message = String(error?.message || error || '');
  return (
    message.includes('Execution context was destroyed') ||
    message.includes('Cannot find context with specified id') ||
    message.includes('Inspected target navigated or closed')
  );
}

async function retryPageAction(action, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      return await action();
    } catch (error) {
      if (!isRetryableExecutionError(error)) {
        throw error;
      }

      lastError = error;
      await delay(200);
    }
  }

  fail(
    `Timed out while retrying ${label} after page execution context resets.\n` +
      `${lastError?.stack || lastError?.message || String(lastError)}`,
  );
}

async function createPage(browser, siteUrl, timeoutMs) {
  const page = await browser.newPage();
  const consoleMessages = ringBuffer(100);
  const pageErrors = ringBuffer(50);

  page.setDefaultTimeout(timeoutMs);
  page.setDefaultNavigationTimeout(timeoutMs);
  page.on('console', (message) => {
    consoleMessages.push(`[${message.type()}] ${message.text()}`);
  });
  page.on('pageerror', (error) => {
    pageErrors.push(String(error?.stack || error?.message || error));
  });

  await page.goto(siteUrl, {
    waitUntil: 'domcontentloaded',
    timeout: timeoutMs,
  });
  await waitForDebugApi(page, timeoutMs);

  return { page, consoleMessages, pageErrors };
}

async function waitForDebugApi(page, timeoutMs) {
  await page.waitForFunction(() => Boolean(globalThis.window && window.__URDF_STUDIO_DEBUG__), {
    timeout: timeoutMs,
  });

  try {
    await page.evaluate(async () => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const candidateNames = ['ping', 'healthCheck', 'healthcheck', 'ready'];
      for (const name of candidateNames) {
        if (typeof api?.[name] === 'function') {
          await api[name]();
          return;
        }
      }
    });
  } catch {
    // ping is optional
  }
}

async function waitForExpectedRobot(page, robotName, timeoutMs) {
  await retryPageAction(
    () =>
      page.waitForFunction(
        (expectedRobotName) => {
          const api = window.__URDF_STUDIO_DEBUG__;
          const snapshot = api?.getRegressionSnapshot?.();
          const documentLoadState = api?.getDocumentLoadState?.();
          const storeRobotName = snapshot?.store?.name ?? null;
          const runtimeRobotName = snapshot?.runtime?.name ?? null;
          return (
            documentLoadState?.status === 'ready' &&
            (storeRobotName === expectedRobotName || runtimeRobotName === expectedRobotName)
          );
        },
        { timeout: Math.min(timeoutMs, 5_000) },
        robotName,
      ),
    timeoutMs,
    `robot "${robotName}" to load`,
  );
}

async function clickElementByText(page, selector, text, timeoutMs) {
  await retryPageAction(
    () =>
      page.waitForFunction(
        ({ elementSelector, expectedText }) => {
          const elements = Array.from(document.querySelectorAll(elementSelector));
          const match = elements.find((element) => element.textContent?.trim() === expectedText);
          return Boolean(match);
        },
        { timeout: Math.min(timeoutMs, 5_000) },
        { elementSelector: selector, expectedText: text },
      ),
    timeoutMs,
    `element ${selector} with text "${text}" to appear`,
  );

  const clicked = await retryPageAction(
    () =>
      page.evaluate(
        ({ elementSelector, expectedText }) => {
          const elements = Array.from(document.querySelectorAll(elementSelector));
          const match = elements.find((element) => element.textContent?.trim() === expectedText);
          if (!(match instanceof HTMLElement)) {
            return false;
          }
          match.click();
          return true;
        },
        { elementSelector: selector, expectedText: text },
      ),
    timeoutMs,
    `clicking ${selector} with text "${text}"`,
  );

  if (!clicked) {
    fail(`Could not click ${selector} with text "${text}"`);
  }
}

async function clickLabelByText(page, text, timeoutMs) {
  await retryPageAction(
    () =>
      page.waitForFunction(
        (expectedText) => {
          const labels = Array.from(document.querySelectorAll('label'));
          return labels.some((label) => label.textContent?.includes(expectedText));
        },
        { timeout: Math.min(timeoutMs, 5_000) },
        text,
      ),
    timeoutMs,
    `label containing "${text}" to appear`,
  );

  const clicked = await retryPageAction(
    () =>
      page.evaluate((expectedText) => {
        const labels = Array.from(document.querySelectorAll('label'));
        const match = labels.find((label) => label.textContent?.includes(expectedText));
        if (!(match instanceof HTMLElement)) {
          return false;
        }
        match.click();
        return true;
      }, text),
    timeoutMs,
    `clicking label containing "${text}"`,
  );

  if (!clicked) {
    fail(`Could not click label containing "${text}"`);
  }
}

async function clickLabelByAnyText(page, candidateTexts, timeoutMs) {
  let lastError = null;

  for (const text of candidateTexts) {
    try {
      await clickLabelByText(page, text, timeoutMs);
      return;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError ?? new Error(`Could not click any label matching: ${candidateTexts.join(', ')}`);
}

async function importFixtureZip(page, zipPath, timeoutMs) {
  await page.waitForSelector('input[type="file"]', { timeout: timeoutMs });
  const handles = await page.$$('input[type="file"]');
  if (handles.length === 0) {
    fail('Could not find a file input on the page.');
  }

  let bestHandle = handles[0];
  let bestScore = -1;

  for (const handle of handles) {
    const score = await handle.evaluate((element) => {
      if (!(element instanceof HTMLInputElement) || element.type !== 'file') {
        return -1;
      }
      const accept = (element.accept || '').toLowerCase();
      let value = 0;
      if (accept.includes('.zip') || accept.includes('zip')) value += 100;
      return value;
    });

    if (score > bestScore) {
      bestScore = score;
      bestHandle = handle;
    }
  }

  await bestHandle.uploadFile(zipPath);
}

async function importFixtureFolder(page, fixtureDir, timeoutMs) {
  await page.waitForSelector('input[type="file"]', { timeout: timeoutMs });
  const handles = await page.$$('input[type="file"]');
  if (handles.length === 0) {
    fail('Could not find a folder input on the page.');
  }

  let bestHandle = null;
  for (const handle of handles) {
    const isDirectoryInput = await handle.evaluate((element) => {
      if (!(element instanceof HTMLInputElement) || element.type !== 'file') {
        return false;
      }

      return (
        element.webkitdirectory ||
        element.hasAttribute('webkitdirectory') ||
        element.hasAttribute('directory')
      );
    });

    if (isDirectoryInput) {
      bestHandle = handle;
      break;
    }
  }

  if (!bestHandle) {
    fail('Could not find a directory upload input on the page.');
  }

  const files = await collectFiles(fixtureDir);
  if (files.length === 0) {
    fail(`Fixture directory is empty: ${fixtureDir}`);
  }

  await bestHandle.evaluate((element) => {
    if (element instanceof HTMLInputElement) {
      element.multiple = true;
      element.setAttribute('multiple', '');
    }
  });
  await bestHandle.uploadFile(...files);
}

async function readHoveredSelection(page) {
  return await retryPageAction(
    () =>
      page.evaluate(() => {
        const hovered =
          window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot()?.interaction?.hoveredSelection;
        if (!hovered?.type || !hovered?.id) {
          return null;
        }

        return `${hovered.id}:${hovered.subType}:${hovered.objectIndex ?? 'undefined'}`;
      }),
    10_000,
    'reading hovered selection',
  );
}

async function readSelectionState(page) {
  return await retryPageAction(
    () =>
      page.evaluate(
        () => window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot()?.interaction?.selection ?? null,
      ),
    10_000,
    'reading selection state',
  );
}

async function setViewerToolMode(page, toolMode, timeoutMs) {
  await retryPageAction(
    () =>
      page.evaluate(
        (nextToolMode) => window.__URDF_STUDIO_DEBUG__?.setViewerToolMode(nextToolMode),
        toolMode,
      ),
    timeoutMs,
    `setting viewer tool mode ${toolMode}`,
  );

  await retryPageAction(
    () =>
      page.waitForFunction(
        (expectedToolMode) =>
          window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot()?.viewer?.toolMode ===
          expectedToolMode,
        { timeout: Math.min(timeoutMs, 5_000) },
        toolMode,
      ),
    timeoutMs,
    `waiting for tool mode ${toolMode}`,
  );
}

async function getProjectedInteractionTargets(page, timeoutMs) {
  return await retryPageAction(
    () =>
      page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getProjectedInteractionTargets?.() ?? []),
    timeoutMs,
    'reading projected interaction targets',
  );
}

async function captureCanvasBox(page) {
  return await retryPageAction(
    () =>
      page.evaluate(() => {
        const canvas = document.querySelector('canvas');
        if (!(canvas instanceof HTMLCanvasElement)) {
          return null;
        }
        const rect = canvas.getBoundingClientRect();
        return {
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
        };
      }),
    10_000,
    'capturing canvas bounds',
  );
}

async function readSceneStatus(page, robotName) {
  return await retryPageAction(
    () =>
      page.evaluate(
        ({ expectedRobotName }) => {
          const api = window.__URDF_STUDIO_DEBUG__;
          const snapshot = api?.getRegressionSnapshot?.() ?? null;
          const documentLoadState = api?.getDocumentLoadState?.() ?? null;
          const bodyText = document.body?.innerText ?? '';
          const canvas = document.querySelector('canvas');
          const storeRobotName = snapshot?.store?.name ?? null;
          const runtimeRobotName = snapshot?.runtime?.name ?? null;
          const documentStatus = documentLoadState?.status ?? null;
          const documentError = documentLoadState?.error ?? null;
          return {
            hasRobot:
              storeRobotName === expectedRobotName || runtimeRobotName === expectedRobotName,
            hasCanvas: canvas instanceof HTMLCanvasElement,
            activeLoadingTexts:
              documentStatus === 'loading' || documentStatus === 'hydrating'
                ? [documentStatus]
                : [],
            activeErrorTexts:
              documentStatus === 'error' ? [documentError || 'document-load-error'] : [],
            documentStatus,
            documentFileName: documentLoadState?.fileName ?? null,
            bodyExcerpt: bodyText.slice(0, 2000),
          };
        },
        { expectedRobotName: robotName },
      ),
    10_000,
    `reading scene status for ${robotName}`,
  );
}

async function waitForSceneToSettle(page, robotName, timeoutMs, stableMs = 1_200) {
  const deadline = Date.now() + timeoutMs;
  let stableSince = null;
  let lastStatus = null;

  while (Date.now() < deadline) {
    const status = await readSceneStatus(page, robotName);
    lastStatus = status;

    if (status.activeErrorTexts.length > 0) {
      fail(
        `Scene entered an error state while waiting for ${robotName}: ` +
          `${status.activeErrorTexts.join(', ')}\n` +
          `Body excerpt:\n${status.bodyExcerpt}`,
      );
    }

    const isStable = status.hasRobot && status.hasCanvas && status.activeLoadingTexts.length === 0;

    if (isStable) {
      if (stableSince == null) {
        stableSince = Date.now();
      } else if (Date.now() - stableSince >= stableMs) {
        return status;
      }
    } else {
      stableSince = null;
    }

    await delay(200);
  }

  fail(
    `Timed out waiting for the ${robotName} scene to settle.\n` +
      `Last status: ${JSON.stringify(lastStatus, null, 2)}`,
  );
}

async function samplePoint(page, canvasBox, point) {
  const x = Math.round(canvasBox.x + point.dx);
  const y = Math.round(canvasBox.y + point.dy);
  await page.mouse.move(x, y);
  await delay(80);
  const hovered = await readHoveredSelection(page);
  return {
    name: point.name,
    client: { x, y },
    expected: point.expected,
    hovered,
    matched: hovered === point.expected,
  };
}

async function runGridScan(page, canvasBox, timeoutMs) {
  const records = [];
  const recordPoint = async (x, y) => {
    if (
      x < canvasBox.x + 1 ||
      x > canvasBox.x + canvasBox.width - 1 ||
      y < canvasBox.y + 1 ||
      y > canvasBox.y + canvasBox.height - 1
    ) {
      return;
    }

    await page.mouse.move(x, y);
    await delay(80);
    const hovered = await readHoveredSelection(page);
    if (hovered) {
      records.push({
        dx: x - canvasBox.x,
        dy: y - canvasBox.y,
        x,
        y,
        hovered,
      });
    }
  };

  for (let dy = 40; dy <= Math.round(canvasBox.height) - 40; dy += 24) {
    for (let dx = 40; dx <= Math.round(canvasBox.width) - 40; dx += 24) {
      const x = Math.round(canvasBox.x + dx);
      const y = Math.round(canvasBox.y + dy);
      await recordPoint(x, y);
    }
  }

  const projectedTargets = await getProjectedInteractionTargets(page, timeoutMs);
  const sampledTargetKeys = new Set();
  const probeTargets = [...projectedTargets]
    .filter((target) => target?.type === 'link' && target?.subType === 'visual')
    .sort(
      (left, right) =>
        (right.projectedArea ?? 0) - (left.projectedArea ?? 0) ||
        String(left.id ?? '').localeCompare(String(right.id ?? '')),
    );

  for (const target of probeTargets) {
    const targetKey = `${target.id}:${target.subType}:${target.objectIndex ?? 'undefined'}`;
    if (sampledTargetKeys.has(targetKey)) {
      continue;
    }
    sampledTargetKeys.add(targetKey);

    for (const [offsetX, offsetY] of PROJECTED_TARGET_PROBE_OFFSETS) {
      await recordPoint(
        Math.round((target.clientX ?? 0) + offsetX),
        Math.round((target.clientY ?? 0) + offsetY),
      );
    }

    if (sampledTargetKeys.size >= 24) {
      break;
    }
  }

  const summaryMap = new Map();
  for (const record of records) {
    const existing = summaryMap.get(record.hovered) ?? {
      target: record.hovered,
      count: 0,
      points: [],
    };
    existing.count += 1;
    if (existing.points.length < 6) {
      existing.points.push({ x: record.x, y: record.y });
    }
    summaryMap.set(record.hovered, existing);
  }

  const summary = [...summaryMap.values()].sort(
    (left, right) => right.count - left.count || left.target.localeCompare(right.target),
  );
  const pointBounds =
    records.length > 0
      ? {
          minX: Math.min(...records.map((record) => record.x)),
          maxX: Math.max(...records.map((record) => record.x)),
          minY: Math.min(...records.map((record) => record.y)),
          maxY: Math.max(...records.map((record) => record.y)),
        }
      : null;

  return {
    records,
    hoveredCount: records.length,
    uniqueHoveredTargets: summary,
    pointBounds,
  };
}

async function clickCanvasPoint(page, point) {
  await page.mouse.move(point.x, point.y);
  await delay(50);
  await page.mouse.click(point.x, point.y, { delay: 20 });
}

async function primeCanvasInteraction(page, canvasBox) {
  const centerPoint = {
    x: Math.round(canvasBox.x + canvasBox.width / 2),
    y: Math.round(canvasBox.y + canvasBox.height / 2),
  };
  await clickCanvasPoint(page, centerPoint);
  await delay(120);
}

async function findLinkSelectionCandidate(page, records) {
  const triedTargets = new Set();

  for (const record of records) {
    if (triedTargets.has(record.hovered)) {
      continue;
    }
    triedTargets.add(record.hovered);

    await clickCanvasPoint(page, record);
    await delay(180);
    const selection = await readSelectionState(page);
    if (selection?.type !== 'link' || !selection.id) {
      continue;
    }

    return {
      point: record,
      selection,
    };
  }

  return null;
}

function summarizeExpectedTargets(grid, targets) {
  const foundTargets = targets
    .map(
      (target) =>
        grid.uniqueHoveredTargets.find((entry) => entry.target.startsWith(target)) ?? null,
    )
    .filter(Boolean);

  const missingTargets = targets.filter(
    (target) => !grid.uniqueHoveredTargets.some((entry) => entry.target.startsWith(target)),
  );

  return {
    foundTargets,
    missingTargets,
  };
}

function assertRegressionResults(result) {
  const failures = [];

  for (const sample of result.samples) {
    if (!sample.matched) {
      failures.push(
        `${sample.name}: expected ${sample.expected ?? 'null'}, got ${sample.hovered ?? 'null'}`,
      );
    }
  }

  if (result.grid.hoveredCount <= 0) {
    failures.push('Grid scan did not produce any hovered points.');
  }

  const topTarget = result.grid.uniqueHoveredTargets[0]?.target ?? null;
  if (!topTarget?.startsWith('lh_forearm_geom_1:visual:')) {
    failures.push(
      `Expected dominant hovered target to be lh_forearm_geom_1:visual:*, got ${topTarget ?? 'null'}`,
    );
  }

  if ((result.grid.uniqueHoveredTargets[0]?.count ?? 0) < 5) {
    failures.push('Expected lh_forearm_geom_1 to dominate at least 5 grid samples.');
  }

  for (const target of result.targetPresence.missingTargets) {
    failures.push(`Grid scan did not include expected target ${target}`);
  }

  const clickHoverRegression = result.clickHoverRegression;
  if (!clickHoverRegression?.selectedLink?.id) {
    failures.push(
      'Could not find a canvas point that click-selects a link for the click-hover regression.',
    );
  } else {
    if ((clickHoverRegression.postClickGrid?.hoveredCount ?? 0) <= 0) {
      failures.push('Post-click grid scan did not produce any hovered points.');
    }

    if ((clickHoverRegression.postClickOtherHoveredTargets?.length ?? 0) <= 0) {
      failures.push(
        `After selecting link ${clickHoverRegression.selectedLink.id}, hover never moved onto a different link.`,
      );
    }
  }

  if (failures.length > 0) {
    fail(`shadow_hand hover regression failed:\n- ${failures.join('\n- ')}`);
  }
}

async function writeJsonAtomic(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await fs.rename(tempPath, filePath);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const zipInfo = await zipFixtureDirectory(options.fixtureDir, options.zipPath);
  const site = await ensureSite(options.siteUrl, options);
  const browser = await launchBrowser(options);
  const expectedRobotName = 'left_shadow_hand';

  try {
    const { page, consoleMessages, pageErrors } = await createPage(
      browser,
      options.siteUrl,
      options.timeoutMs,
    );

    await importFixtureFolder(page, options.fixtureDir, options.timeoutMs);
    try {
      await waitForExpectedRobot(page, expectedRobotName, 30_000);
    } catch (folderImportError) {
      await page.goto(options.siteUrl, {
        waitUntil: 'domcontentloaded',
        timeout: options.timeoutMs,
      });
      await waitForDebugApi(page, options.timeoutMs);
      await importFixtureZip(page, options.zipPath, options.timeoutMs);
      await waitForExpectedRobot(page, expectedRobotName, options.timeoutMs);
    }
    await waitForSceneToSettle(page, expectedRobotName, options.timeoutMs);

    await waitForSceneToSettle(page, expectedRobotName, options.timeoutMs);
    await clickLabelByAnyText(page, ['Show Visual', 'Show Geometry'], options.timeoutMs);
    await waitForSceneToSettle(page, expectedRobotName, options.timeoutMs);
    await clickElementByText(page, 'button', 'Auto Fit', options.timeoutMs);
    await waitForSceneToSettle(page, expectedRobotName, options.timeoutMs, 800);
    await setViewerToolMode(page, 'select', options.timeoutMs);

    const canvasBox = await captureCanvasBox(page);
    if (!canvasBox) {
      fail('Could not locate canvas bounding box.');
    }
    await primeCanvasInteraction(page, canvasBox);

    const samples = [];
    for (const point of FIXED_SAMPLE_POINTS) {
      samples.push(await samplePoint(page, canvasBox, point));
    }

    const grid = await runGridScan(page, canvasBox, options.timeoutMs);
    const targetPresence = summarizeExpectedTargets(grid, EXPECTED_FRONT_TARGETS);

    const clickSelectionCandidate = await findLinkSelectionCandidate(page, grid.records);
    const postClickGrid = clickSelectionCandidate
      ? await runGridScan(page, canvasBox, options.timeoutMs)
      : {
          records: [],
          hoveredCount: 0,
          uniqueHoveredTargets: [],
          pointBounds: null,
        };
    const postClickOtherHoveredTargets = clickSelectionCandidate
      ? postClickGrid.uniqueHoveredTargets.filter((entry) => {
          return !entry.target.startsWith(`${clickSelectionCandidate.selection.id}:`);
        })
      : [];

    await page.screenshot({
      path: options.screenshotPath,
      type: 'png',
    });

    const result = {
      fixtureDir: options.fixtureDir,
      zipPath: options.zipPath,
      zipFileCount: zipInfo.fileCount,
      siteUrl: options.siteUrl,
      viewport: DEFAULT_VIEWPORT,
      canvasBox,
      samples,
      grid,
      targetPresence,
      clickHoverRegression: {
        clickPoint: clickSelectionCandidate?.point ?? null,
        selectedLink: clickSelectionCandidate?.selection ?? null,
        postClickGrid: {
          hoveredCount: postClickGrid.hoveredCount,
          uniqueHoveredTargets: postClickGrid.uniqueHoveredTargets,
          pointBounds: postClickGrid.pointBounds,
        },
        postClickOtherHoveredTargets,
      },
      screenshotPath: options.screenshotPath,
      consoleMessages: consoleMessages.snapshot(),
      pageErrors: pageErrors.snapshot(),
      generatedAt: new Date().toISOString(),
    };

    await writeJsonAtomic(options.outputPath, result);
    assertRegressionResults(result);

    console.log(
      JSON.stringify(
        {
          ok: true,
          outputPath: options.outputPath,
          screenshotPath: options.screenshotPath,
          topTarget: result.grid.uniqueHoveredTargets[0]?.target ?? null,
          hoveredCount: result.grid.hoveredCount,
        },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
    await site.stop();
  }
}

main().catch(async (error) => {
  if (typeof page !== 'undefined') {
    await page.screenshot({ path: 'tmp/regression/error.png' });
  }
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
