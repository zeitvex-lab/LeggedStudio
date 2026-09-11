#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import puppeteer from 'puppeteer';

const DEFAULT_SITE_URL = 'http://127.0.0.1:4173';
const DEFAULT_SITE_TIMEOUT_MS = 120_000;
const DEFAULT_OPERATION_TIMEOUT_MS = 240_000;
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/unitree_ros_usd_export_benchmark.json');
const DEFAULT_START_COMMAND = (host, port) => `npm run dev -- --host ${host} --port ${port}`;
const DEFAULT_EXECUTABLE_CANDIDATES = [
  process.env.CHROME_PATH,
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium',
].filter(Boolean);
const ASSET_EXTENSIONS = new Set([
  '.dae',
  '.obj',
  '.stl',
  '.gltf',
  '.glb',
  '.png',
  '.jpg',
  '.jpeg',
  '.bmp',
  '.gif',
  '.webp',
  '.mtl',
]);
const IDENTITY_TRANSFORM = Object.freeze({
  position: { x: 0, y: 0, z: 0 },
  rotation: { r: 0, p: 0, y: 0 },
});
const SAMPLE_DEFINITIONS = [
  {
    id: 'b2',
    label: 'b2_description',
    mode: 'single',
    exportName: 'b2_description',
    maxTotalMs: 11_000,
    maxSceneMs: 8_000,
    inputs: [
      {
        urdfRelative: 'test/unitree_ros/robots/b2_description/urdf/b2_description.urdf',
        assetRootRelative: 'test/unitree_ros/robots/b2_description',
      },
    ],
  },
  {
    id: 'g1-dual-arm',
    label: 'g1_dual_arm',
    mode: 'single',
    exportName: 'g1_dual_arm',
    maxTotalMs: 10_000,
    maxSceneMs: 8_000,
    inputs: [
      {
        urdfRelative: 'test/unitree_ros/robots/g1_description/g1_dual_arm.urdf',
        assetRootRelative: 'test/unitree_ros/robots/g1_description',
      },
    ],
  },
  {
    id: 'assembly',
    label: 'b2 + g1_dual_arm assembly',
    mode: 'assembly',
    exportName: 'b2_g1_dual_arm_assembly',
    maxTotalMs: 12_000,
    maxSceneMs: 8_500,
    inputs: [
      {
        urdfRelative: 'test/unitree_ros/robots/b2_description/urdf/b2_description.urdf',
        assetRootRelative: 'test/unitree_ros/robots/b2_description',
        componentId: 'comp_b2',
        rootName: 'b2',
        transform: IDENTITY_TRANSFORM,
      },
      {
        urdfRelative: 'test/unitree_ros/robots/g1_description/g1_dual_arm.urdf',
        assetRootRelative: 'test/unitree_ros/robots/g1_description',
        componentId: 'comp_g1_dual_arm',
        rootName: 'g1_dual_arm',
        transform: {
          position: { x: 2.5, y: 0, z: 0 },
          rotation: { r: 0, p: 0, y: 0 },
        },
      },
    ],
  },
];

const HELP_TEXT = `Usage:
  node scripts/test/benchmark/benchmark_unitree_usd_export.mjs [options]

Options:
  --site-url <url>          Dev site URL. Default: ${DEFAULT_SITE_URL}
  --output <path>           Output JSON path. Default: ${DEFAULT_OUTPUT_PATH}
  --model <id>              Restrict to one sample id. Repeatable. Valid: ${SAMPLE_DEFINITIONS.map((sample) => sample.id).join(', ')}
  --site-timeout-ms <ms>    Site startup timeout. Default: ${DEFAULT_SITE_TIMEOUT_MS}
  --timeout-ms <ms>         Per-sample timeout. Default: ${DEFAULT_OPERATION_TIMEOUT_MS}
  --start-command <cmd>     Override auto-start command.
  --chrome-path <path>      Browser executable path.
  --no-start                Fail if the site is offline.
  --no-assert               Do not fail on threshold regressions.
  --headed                  Launch headed browser.
  --help                    Show this help.
`;

function normalizePath(value) {
  return String(value || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '');
}

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
    outputPath: DEFAULT_OUTPUT_PATH,
    models: [],
    siteTimeoutMs: DEFAULT_SITE_TIMEOUT_MS,
    timeoutMs: DEFAULT_OPERATION_TIMEOUT_MS,
    startCommand: null,
    chromePath: null,
    noStart: false,
    assertThresholds: true,
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
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--model':
        options.models.push(nextValue());
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
      case '--chrome-path':
        options.chromePath = path.resolve(nextValue());
        break;
      case '--no-start':
        options.noStart = true;
        break;
      case '--no-assert':
        options.assertThresholds = false;
        break;
      case '--headed':
        options.headed = true;
        break;
      case '--help':
      case '-h':
        console.log(HELP_TEXT);
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  options.models = [...new Set(options.models.map((value) => value.trim()).filter(Boolean))];
  return options;
}

async function writeJsonAtomic(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await fs.rename(tempPath, filePath);
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
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

async function waitForSite(siteUrl, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isSiteReachable(siteUrl, timeoutMs)) {
      return true;
    }
    await delay(1_000);
  }
  return false;
}

function deriveStartCommand(siteUrl, explicitCommand) {
  if (explicitCommand) {
    return explicitCommand;
  }
  const url = new URL(siteUrl);
  const host = url.hostname || '127.0.0.1';
  const port = url.port || '4173';
  return DEFAULT_START_COMMAND(host, port);
}

async function isSourceImportsReachable(siteUrl, timeoutMs) {
  try {
    const probeUrl = new URL(
      '/src/features/file-io/utils/usdExportCoordinator.ts',
      siteUrl,
    ).toString();
    const response = await fetchWithTimeout(probeUrl, Math.min(timeoutMs, 10_000));
    return response.ok;
  } catch {
    return false;
  }
}

async function ensureSiteAvailable(options) {
  if (await isSiteReachable(options.siteUrl, options.siteTimeoutMs)) {
    if (await isSourceImportsReachable(options.siteUrl, options.siteTimeoutMs)) {
      return { startedProcess: null };
    }

    fail(
      `Site is reachable but does not expose direct /src module imports: ${options.siteUrl}. ` +
        'Use a Vite dev server, not preview.',
    );
  }

  if (options.noStart) {
    fail(`Site is offline and --no-start was provided: ${options.siteUrl}`);
  }

  const startCommand = deriveStartCommand(options.siteUrl, options.startCommand);
  const child = spawn(startCommand, {
    cwd: process.cwd(),
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
    env: {
      ...process.env,
      CHOKIDAR_USEPOLLING: process.env.CHOKIDAR_USEPOLLING || '1',
      CHOKIDAR_INTERVAL: process.env.CHOKIDAR_INTERVAL || '200',
    },
  });
  child.stdout.on('data', (chunk) => process.stderr.write(chunk));
  child.stderr.on('data', (chunk) => process.stderr.write(chunk));

  const ready = await waitForSite(options.siteUrl, options.siteTimeoutMs);
  if (!ready) {
    child.kill('SIGTERM');
    fail(`Timed out waiting for site to become reachable: ${options.siteUrl}`);
  }

  if (!(await isSourceImportsReachable(options.siteUrl, options.siteTimeoutMs))) {
    child.kill('SIGTERM');
    fail(
      `Started site but direct /src module imports are still unavailable: ${options.siteUrl}. ` +
        'This benchmark requires a Vite dev server.',
    );
  }

  return { startedProcess: child };
}

function resolveExecutablePath(explicitChromePath) {
  if (explicitChromePath) {
    return explicitChromePath;
  }
  return DEFAULT_EXECUTABLE_CANDIDATES.find(Boolean) ?? null;
}

async function collectAssetFiles(rootDir, baseDir = rootDir) {
  const results = [];
  const entries = await fs.readdir(rootDir, { withFileTypes: true });
  entries.sort((left, right) => left.name.localeCompare(right.name));

  for (const entry of entries) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      results.push(...(await collectAssetFiles(absolutePath, baseDir)));
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }

    const extension = path.extname(entry.name).toLowerCase();
    if (!ASSET_EXTENSIONS.has(extension)) {
      continue;
    }

    results.push({
      absolutePath,
      relativePath: path.relative(baseDir, absolutePath).split(path.sep).join('/'),
    });
  }

  return results;
}

const assetDescriptorCache = new Map();

async function buildAssetDescriptors(assetRootRelative) {
  const normalizedRoot = normalizePath(assetRootRelative);
  const cached = assetDescriptorCache.get(normalizedRoot);
  if (cached) {
    return cached;
  }

  const assetRootAbsolute = path.resolve(normalizedRoot);
  if (!(await fileExists(assetRootAbsolute))) {
    fail(`Asset root does not exist: ${assetRootRelative}`);
  }

  const packageName = path.basename(assetRootAbsolute);
  const assetFiles = await collectAssetFiles(assetRootAbsolute);
  const descriptors = assetFiles.map(({ absolutePath, relativePath }) => ({
    urlPath: `/${normalizePath(path.relative(process.cwd(), absolutePath))}`,
    aliases: [
      relativePath,
      `${packageName}/${relativePath}`,
      `package://${packageName}/${relativePath}`,
    ],
  }));

  assetDescriptorCache.set(normalizedRoot, descriptors);
  return descriptors;
}

async function resolveSamples(options) {
  const allSamples = await Promise.all(
    SAMPLE_DEFINITIONS.map(async (sample) => ({
      ...sample,
      inputs: await Promise.all(
        sample.inputs.map(async (input) => ({
          ...input,
          urdfUrlPath: `/${normalizePath(input.urdfRelative)}`,
          assetDescriptors: await buildAssetDescriptors(input.assetRootRelative),
        })),
      ),
    })),
  );

  if (options.models.length === 0) {
    return allSamples;
  }

  const selected = new Set(options.models.map((value) => value.toLowerCase()));
  const filtered = allSamples.filter((sample) => selected.has(sample.id.toLowerCase()));
  if (filtered.length === 0) {
    fail(`No sample matched --model filters: ${options.models.join(', ')}`);
  }
  return filtered;
}

async function openFreshPage(browser, siteUrl, timeoutMs) {
  let lastError = null;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1024, deviceScaleFactor: 1 });
    await page.setCacheEnabled(false);
    page.setDefaultTimeout(timeoutMs);

    try {
      await page.goto(siteUrl, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
      await delay(500);
      return page;
    } catch (error) {
      lastError = error;
      await page.close().catch(() => {});

      const message = error instanceof Error ? error.message : String(error);
      if (!/frame got detached|Navigating frame was detached/i.test(message) || attempt === 2) {
        throw error;
      }

      await delay(750);
    }
  }

  throw lastError ?? new Error(`Unable to open benchmark page: ${siteUrl}`);
}

async function assertSourceImportsAvailable(page) {
  const probe = await page.evaluate(async () => {
    try {
      await import('/src/features/file-io/utils/usdExportCoordinator.ts');
      return { ok: true, message: null };
    } catch (error) {
      return {
        ok: false,
        message: error instanceof Error ? error.message : String(error),
      };
    }
  });

  if (!probe?.ok) {
    fail(
      `The target site does not support direct /src module imports. Use a Vite dev server, not preview. Details: ${probe?.message || 'unknown error'}`,
    );
  }
}

function isRetryableRuntimeError(value) {
  const message = String(value || '');
  return /Execution context was destroyed|frame got detached|Navigating frame was detached/i.test(
    message,
  );
}

async function warmupSourceImports(browser, siteUrl, timeoutMs) {
  let lastError = null;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const page = await openFreshPage(browser, siteUrl, timeoutMs);
    try {
      await page.evaluate(async () => {
        await Promise.all([
          import('/src/core/parsers/urdf/parser/index.ts'),
          import('/src/features/file-io/utils/usdExportCoordinator.ts'),
          import('/src/core/robot/assemblyComponentPreparation.ts'),
          import('/src/core/robot/assemblyTransforms.ts'),
        ]);
        return true;
      });
      return;
    } catch (error) {
      lastError = error;
      if (
        !isRetryableRuntimeError(error instanceof Error ? error.message : String(error)) ||
        attempt === 2
      ) {
        throw error;
      }
      await delay(750);
    } finally {
      await page.close().catch(() => {});
    }
  }

  throw lastError ?? new Error('Unable to warm up source imports for USD export benchmark.');
}

function createRingBuffer(limit = 100) {
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

async function benchmarkSample(page, sample) {
  return await page.evaluate(async (sampleInput) => {
    const normalizePath = (value) =>
      String(value || '')
        .replace(/\\/g, '/')
        .replace(/^\/+/, '');
    const toUrl = (value) => {
      if (/^https?:\/\//i.test(value)) {
        return value;
      }
      return new URL(value.startsWith('/') ? value : `/${normalizePath(value)}`, location.origin)
        .href;
    };
    const toRobotState = (robotData) => ({
      ...robotData,
      selection: {
        type: 'link',
        id: robotData.rootLinkId ?? null,
      },
    });
    const meshType = 'mesh';
    const identityTransform = {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    };
    const collectMeshReferences = (robotData) => {
      const unique = new Set();
      const visitVisual = (visual) => {
        if (
          !visual ||
          String(visual.type || '')
            .trim()
            .toLowerCase() !== meshType
        ) {
          return;
        }
        const meshPath = String(visual.meshPath || visual.filename || '').trim();
        if (meshPath) {
          unique.add(meshPath);
        }
      };

      for (const link of Object.values(robotData.links || {})) {
        visitVisual(link.visual);
        visitVisual(link.collision);
        for (const collisionBody of link.collisionBodies || []) {
          visitVisual(collisionBody);
        }
      }

      return [...unique].sort((left, right) => left.localeCompare(right));
    };

    const [parserModule, exportModule, assemblyPreparationModule, assemblyTransformsModule] =
      await Promise.all([
        import('/src/core/parsers/urdf/parser/index.ts'),
        import('/src/features/file-io/utils/usdExportCoordinator.ts'),
        import('/src/core/robot/assemblyComponentPreparation.ts'),
        import('/src/core/robot/assemblyTransforms.ts'),
      ]);

    const { parseURDF } = parserModule;
    const { exportRobotToUsd } = exportModule;
    const { namespaceAssemblyRobotData } = assemblyPreparationModule;
    const { buildExportableAssemblyRobotData } = assemblyTransformsModule;

    const blobPromiseCache = new Map();
    const fetchBlob = async (url) => {
      if (blobPromiseCache.has(url)) {
        return await blobPromiseCache.get(url);
      }

      const request = fetch(url, { cache: 'no-store' }).then(async (response) => {
        if (!response.ok) {
          throw new Error(`Failed to fetch asset ${url}: ${response.status}`);
        }
        return await response.blob();
      });
      blobPromiseCache.set(url, request);
      return await request;
    };

    const buildExtraMeshFiles = async (assetDescriptors) => {
      const extraMeshFiles = new Map();

      for (const descriptor of assetDescriptors) {
        const blob = await fetchBlob(toUrl(descriptor.urlPath));
        descriptor.aliases.forEach((alias) => {
          const normalizedAlias = normalizePath(alias);
          if (normalizedAlias && !extraMeshFiles.has(normalizedAlias)) {
            extraMeshFiles.set(normalizedAlias, blob);
          }
        });
      }

      return extraMeshFiles;
    };

    const mergeExtraMeshFiles = (maps) => {
      const merged = new Map();
      maps.forEach((map) => {
        map.forEach((blob, key) => {
          if (!merged.has(key)) {
            merged.set(key, blob);
          }
        });
      });
      return merged;
    };

    const loadedInputs = [];
    for (const input of sampleInput.inputs) {
      const urdfResponse = await fetch(toUrl(input.urdfUrlPath), { cache: 'no-store' });
      if (!urdfResponse.ok) {
        throw new Error(`Failed to fetch URDF ${input.urdfUrlPath}: ${urdfResponse.status}`);
      }

      const urdfText = await urdfResponse.text();
      const parsedRobot = parseURDF(urdfText);
      if (!parsedRobot) {
        throw new Error(`Failed to parse URDF ${input.urdfUrlPath}`);
      }

      loadedInputs.push({
        input,
        robot: parsedRobot,
        extraMeshFiles: await buildExtraMeshFiles(input.assetDescriptors),
        meshReferences: collectMeshReferences(parsedRobot),
      });
    }

    const uniqueMeshReferences = new Set();
    loadedInputs.forEach((entry) => {
      entry.meshReferences.forEach((meshReference) => uniqueMeshReferences.add(meshReference));
    });

    let exportRobot;
    let extraMeshFiles;

    if (sampleInput.mode === 'assembly') {
      const components = Object.create(null);
      loadedInputs.forEach((entry) => {
        components[entry.input.componentId] = {
          id: entry.input.componentId,
          name: entry.input.rootName,
          sourceFile: entry.input.urdfUrlPath,
          robot: namespaceAssemblyRobotData(entry.robot, {
            componentId: entry.input.componentId,
            rootName: entry.input.rootName,
          }),
          transform: entry.input.transform || identityTransform,
          visible: true,
        };
      });

      exportRobot = buildExportableAssemblyRobotData({
        name: sampleInput.exportName,
        transform: identityTransform,
        components,
        bridges: {},
      });
      extraMeshFiles = mergeExtraMeshFiles(loadedInputs.map((entry) => entry.extraMeshFiles));
    } else {
      exportRobot = loadedInputs[0].robot;
      extraMeshFiles = loadedInputs[0].extraMeshFiles;
    }

    const robotState = toRobotState(exportRobot);
    const phaseStarts = Object.create(null);
    const phaseEnds = Object.create(null);
    const phaseLastSeen = Object.create(null);
    const totalStart = performance.now();
    let progressEventCount = 0;

    const payload = await exportRobotToUsd({
      robot: robotState,
      exportName: sampleInput.exportName,
      assets: {},
      extraMeshFiles,
      meshCompression: {
        enabled: true,
        quality: 50,
      },
      fileFormat: 'usda',
      layoutProfile: 'isaacsim',
      onProgress: (progress) => {
        const now = performance.now();
        const phase = String(progress.phase || '');
        if (!phase) {
          return;
        }

        if (phaseStarts[phase] == null) {
          phaseStarts[phase] = now;
        }
        phaseLastSeen[phase] = now;
        progressEventCount += 1;

        if (Number(progress.total) > 0 && Number(progress.completed) >= Number(progress.total)) {
          phaseEnds[phase] = now;
        }
      },
    });

    const totalMs = Math.round(performance.now() - totalStart);
    const phaseMs = {};
    for (const phase of ['links', 'geometry', 'scene', 'assets']) {
      if (phaseStarts[phase] == null) {
        continue;
      }

      const stop = phaseEnds[phase] ?? phaseLastSeen[phase] ?? performance.now();
      phaseMs[phase] = Math.round(stop - phaseStarts[phase]);
    }

    return {
      totalMs,
      phaseMs,
      progressEventCount,
      archiveFileCount: payload.archiveFiles.size,
      rootLayerPath: payload.rootLayerPath,
      contentLength: payload.content.length,
      linkCount: Object.keys(robotState.links || {}).length,
      jointCount: Object.keys(robotState.joints || {}).length,
      inputModelCount: loadedInputs.length,
      uniqueMeshCount: uniqueMeshReferences.size,
      assetFileCount: loadedInputs.reduce(
        (count, entry) => count + entry.input.assetDescriptors.length,
        0,
      ),
    };
  }, sample);
}

function buildSampleResult(sample, benchmark, consoleErrors) {
  const failures = [];
  if (!benchmark || typeof benchmark.totalMs !== 'number') {
    failures.push('missing benchmark payload');
  }

  const sceneMs = Number(benchmark?.phaseMs?.scene ?? NaN);
  if (Number.isFinite(benchmark?.totalMs) && benchmark.totalMs > sample.maxTotalMs) {
    failures.push(`total ${benchmark.totalMs}ms > budget ${sample.maxTotalMs}ms`);
  }
  if (Number.isFinite(sceneMs) && sceneMs > sample.maxSceneMs) {
    failures.push(`scene ${sceneMs}ms > budget ${sample.maxSceneMs}ms`);
  }
  if (!Number.isFinite(sceneMs)) {
    failures.push('missing scene phase timing');
  }
  if (!Number.isFinite(benchmark?.archiveFileCount) || benchmark.archiveFileCount <= 0) {
    failures.push('archive file count is empty');
  }
  if (!Number.isFinite(benchmark?.contentLength) || benchmark.contentLength <= 0) {
    failures.push('USD root layer content is empty');
  }

  return {
    id: sample.id,
    label: sample.label,
    exportName: sample.exportName,
    budgets: {
      maxTotalMs: sample.maxTotalMs,
      maxSceneMs: sample.maxSceneMs,
    },
    pass: failures.length === 0,
    failures,
    consoleErrorCount: consoleErrors.length,
    consoleErrors,
    ...benchmark,
  };
}

async function stopStartedProcess(startedProcess) {
  if (!startedProcess) {
    return;
  }

  if (startedProcess.exitCode != null || startedProcess.signalCode != null) {
    return;
  }

  startedProcess.kill('SIGTERM');
  await delay(500);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const samples = await resolveSamples(options);
  const site = await ensureSiteAvailable(options);
  const executablePath = resolveExecutablePath(options.chromePath);
  const browser = await puppeteer.launch({
    headless: !options.headed,
    ...(executablePath ? { executablePath } : {}),
  });

  const results = [];

  try {
    await warmupSourceImports(browser, options.siteUrl, options.timeoutMs);

    for (const sample of samples) {
      process.stdout.write(`[usd-export-bench] sample=${sample.id}\n`);
      let result = null;

      for (let attempt = 0; attempt < 2; attempt += 1) {
        const page = await openFreshPage(browser, options.siteUrl, options.timeoutMs);
        const consoleErrors = createRingBuffer(50);

        page.on('console', (message) => {
          if (message.type() === 'error') {
            consoleErrors.push(message.text());
          }
        });

        try {
          await assertSourceImportsAvailable(page);

          const benchmark = await benchmarkSample(page, sample);
          result = buildSampleResult(sample, benchmark, consoleErrors.snapshot());
          if (benchmark.runtimeError) {
            result.failures.unshift(`runtime error: ${benchmark.runtimeError}`);
            result.pass = false;
          }
        } catch (error) {
          result = buildSampleResult(
            sample,
            {
              totalMs: NaN,
              phaseMs: {},
              progressEventCount: 0,
              archiveFileCount: 0,
              rootLayerPath: null,
              contentLength: 0,
              linkCount: 0,
              jointCount: 0,
              inputModelCount: sample.inputs.length,
              uniqueMeshCount: 0,
              assetFileCount: sample.inputs.reduce(
                (count, input) => count + input.assetDescriptors.length,
                0,
              ),
              runtimeError: error instanceof Error ? error.message : String(error),
            },
            consoleErrors.snapshot(),
          );
          result.failures.unshift(`runtime error: ${result.runtimeError}`);
          result.pass = false;

          if (!isRetryableRuntimeError(result.runtimeError) || attempt === 1) {
            break;
          }

          await delay(750);
          continue;
        } finally {
          await page.close().catch(() => {});
        }

        break;
      }

      results.push(result);
      process.stdout.write(
        `[usd-export-bench]   total=${Number.isFinite(result.totalMs) ? result.totalMs : 'n/a'}ms ` +
          `scene=${result.phaseMs?.scene ?? 'n/a'}ms pass=${result.pass}\n`,
      );
    }
  } finally {
    await browser.close().catch(() => {});
    await stopStartedProcess(site.startedProcess);
  }

  const passCount = results.filter((result) => result.pass).length;
  const summary = {
    generatedAtUtc: new Date().toISOString(),
    workspace: process.cwd(),
    siteUrl: options.siteUrl,
    sampleCount: results.length,
    passCount,
    failCount: results.length - passCount,
    samples: results,
  };

  await writeJsonAtomic(options.outputPath, summary);
  process.stdout.write(`[usd-export-bench] output=${options.outputPath}\n`);

  if (options.assertThresholds && summary.failCount > 0) {
    fail(
      `USD export benchmark regression detected: ${JSON.stringify(
        results
          .filter((result) => !result.pass)
          .map((result) => ({
            id: result.id,
            failures: result.failures,
          })),
        null,
        2,
      )}`,
    );
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
