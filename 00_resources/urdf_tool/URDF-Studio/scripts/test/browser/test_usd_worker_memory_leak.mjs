#!/usr/bin/env node

/**
 * USD worker/browser memory regression guard.
 *
 * Repeatedly resets the debug fixture store, imports the Go2 USD fixture in the
 * same page, and samples JS heap, Worker lifecycle counters, and renderer
 * resource counters. The threshold is intentionally conservative: this catches
 * obvious stuck workers / unbounded heap growth without failing on normal
 * one-time caches.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession,
  createTestSuite,
  assert,
  assertGreaterThan,
  getRuntimeTransforms,
  importUnitreeModel,
  waitForReady,
  writeReport,
  printSummary,
} from './helpers/usd-helpers.mjs';

const DEFAULT_CYCLES = 4;
const DEFAULT_MAX_HEAP_GROWTH_MB = 192;
const DEFAULT_MAX_LIVE_WORKERS = 32;
const DEFAULT_MODEL_KEY = 'Go2';
const OPERATION_TIMEOUT_MS = 180_000;

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseNonNegativeNumber(value, fallback) {
  if (value == null || value === '') {
    return fallback;
  }

  const parsed = Number(String(value ?? ''));
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function parseOptions(argv) {
  const options = {
    cycles: parsePositiveInteger(process.env.USD_WORKER_MEMORY_CYCLES, DEFAULT_CYCLES),
    maxHeapGrowthMb: parseNonNegativeNumber(
      process.env.USD_WORKER_MEMORY_MAX_HEAP_GROWTH_MB,
      DEFAULT_MAX_HEAP_GROWTH_MB,
    ),
    maxLiveWorkers: parsePositiveInteger(
      process.env.USD_WORKER_MEMORY_MAX_LIVE_WORKERS,
      DEFAULT_MAX_LIVE_WORKERS,
    ),
    modelKey: process.env.USD_WORKER_MEMORY_MODEL || DEFAULT_MODEL_KEY,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (value == null) throw new Error(`Missing value for ${arg}`);
      index += 1;
      return value;
    };

    switch (arg) {
      case '--cycles':
        options.cycles = parsePositiveInteger(nextValue(), options.cycles);
        break;
      case '--max-heap-growth-mb':
        options.maxHeapGrowthMb = parseNonNegativeNumber(nextValue(), options.maxHeapGrowthMb);
        break;
      case '--max-live-workers':
        options.maxLiveWorkers = parsePositiveInteger(nextValue(), options.maxLiveWorkers);
        break;
      case '--model':
        options.modelKey = nextValue();
        break;
      case '--help':
      case '-h':
        return { help: true, options };
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return { help: false, options };
}

function printHelp() {
  console.log(`Usage: node scripts/test/browser/test_usd_worker_memory_leak.mjs [options]

Options:
  --cycles <n>                 Import cycles. Default: ${DEFAULT_CYCLES}
  --max-heap-growth-mb <mb>    Allowed heap growth after warmup. Default: ${DEFAULT_MAX_HEAP_GROWTH_MB}
  --max-live-workers <n>       Max observed tracked live Workers. Default: ${DEFAULT_MAX_LIVE_WORKERS}
  --model <key>                Unitree USD model key. Default: ${DEFAULT_MODEL_KEY}
  --help                       Show this help.
`);
}

function installWorkerLeakProbe() {
  if (globalThis.__URDF_STUDIO_WORKER_LEAK_PROBE__ || typeof Worker !== 'function') {
    return;
  }

  const OriginalWorker = Worker;
  const stats = {
    created: 0,
    terminated: 0,
    live: 0,
    maxLive: 0,
    urls: [],
  };

  function TrackingWorker(scriptUrl, options) {
    const worker = new OriginalWorker(scriptUrl, options);
    let terminated = false;
    const url = String(scriptUrl ?? '');
    stats.created += 1;
    stats.live += 1;
    stats.maxLive = Math.max(stats.maxLive, stats.live);
    stats.urls.push(url);
    if (stats.urls.length > 40) {
      stats.urls.splice(0, stats.urls.length - 40);
    }

    const originalTerminate = worker.terminate.bind(worker);
    worker.terminate = () => {
      if (!terminated) {
        terminated = true;
        stats.terminated += 1;
        stats.live = Math.max(0, stats.live - 1);
      }
      return originalTerminate();
    };
    return worker;
  }

  TrackingWorker.prototype = OriginalWorker.prototype;
  Object.setPrototypeOf(TrackingWorker, OriginalWorker);
  Object.defineProperty(TrackingWorker, 'name', { value: 'Worker' });

  globalThis.Worker = TrackingWorker;
  globalThis.__URDF_STUDIO_WORKER_LEAK_PROBE__ = {
    getSnapshot: () => ({
      created: stats.created,
      terminated: stats.terminated,
      live: stats.live,
      maxLive: stats.maxLive,
      urls: [...stats.urls],
    }),
  };
}

async function installLeakProbe(page) {
  await page.evaluateOnNewDocument(installWorkerLeakProbe);
  for (const frame of page.frames()) {
    try {
      await frame.evaluate(installWorkerLeakProbe);
    } catch {
      // Frames may detach while the USD runtime is booting.
    }
  }
}

async function resetFixtureFiles(page) {
  const result = await page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.resetFixtureFiles?.() ?? {
    ok: false,
    availableFileCount: -1,
  });
  if (!result?.ok) {
    throw new Error(`Could not reset fixture files: ${JSON.stringify(result)}`);
  }
}

async function forceGarbageCollection(page) {
  try {
    const client = await page.target().createCDPSession();
    await client.send('HeapProfiler.enable').catch(() => undefined);
    await client.send('HeapProfiler.collectGarbage').catch(() => undefined);
    await client.detach().catch(() => undefined);
  } catch {
    // HeapProfiler is best-effort in non-Chromium environments.
  }

  await page.evaluate(() => {
    if (typeof globalThis.gc === 'function') {
      globalThis.gc();
    }
  }).catch(() => undefined);
}

async function getFrameRuntimeSamples(page) {
  const samples = [];
  for (const frame of page.frames()) {
    try {
      const sample = await frame.evaluate(() => ({
        url: location.href,
        workerStats: globalThis.__URDF_STUDIO_WORKER_LEAK_PROBE__?.getSnapshot?.() ?? null,
        renderer: globalThis.renderer
          ? {
              geometries: Number(globalThis.renderer.info?.memory?.geometries ?? 0),
              textures: Number(globalThis.renderer.info?.memory?.textures ?? 0),
              programs: Number(globalThis.renderer.info?.programs?.length ?? 0),
            }
          : null,
        textureMetrics: globalThis.__HYDRA_TEXTURE_METRICS__?.getSnapshot?.() ?? null,
        loadingManagerMetrics: globalThis.__HYDRA_LOADING_MANAGER_METRICS__?.getSnapshot?.() ?? null,
      }));
      samples.push(sample);
    } catch {
      // Ignore detached frames.
    }
  }
  return samples;
}

function aggregateWorkerStats(frameSamples) {
  return frameSamples.reduce(
    (total, frame) => {
      const stats = frame.workerStats;
      if (!stats) return total;
      total.created += Number(stats.created || 0);
      total.terminated += Number(stats.terminated || 0);
      total.live += Number(stats.live || 0);
      total.maxLive = Math.max(total.maxLive, Number(stats.maxLive || 0));
      return total;
    },
    { created: 0, terminated: 0, live: 0, maxLive: 0 },
  );
}

function getActiveWorkerTargets(page) {
  return page
    .browser()
    .targets()
    .filter((target) => ['worker', 'service_worker', 'shared_worker'].includes(target.type()))
    .map((target) => ({
      type: target.type(),
      url: target.url(),
    }))
    .filter((target) => target.url.length > 0);
}

async function sampleMemory(page, label) {
  await forceGarbageCollection(page);
  await delay(500);
  const metrics = await page.metrics();
  const frameSamples = await getFrameRuntimeSamples(page);
  const workerStats = aggregateWorkerStats(frameSamples);
  const activeWorkerTargets = getActiveWorkerTargets(page);
  return {
    label,
    timestamp: Date.now(),
    jsHeapUsedMb: Number(((metrics.JSHeapUsedSize || 0) / 1024 / 1024).toFixed(2)),
    nodes: metrics.Nodes,
    documents: metrics.Documents,
    activeWorkerTargetCount: activeWorkerTargets.length,
    activeWorkerTargets,
    workerStats,
    frames: frameSamples,
  };
}

async function waitForUsdRuntimeTransforms(page, timeoutMs = OPERATION_TIMEOUT_MS) {
  await page.waitForFunction(
    () => {
      const transforms = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.();
      return Object.keys(transforms?.links ?? {}).length > 0;
    },
    { timeout: timeoutMs },
  );
}

async function runCycle(page, cycle, modelKey) {
  await resetFixtureFiles(page);
  await importUnitreeModel(page, modelKey, OPERATION_TIMEOUT_MS);
  await waitForReady(page, OPERATION_TIMEOUT_MS);
  await waitForUsdRuntimeTransforms(page, OPERATION_TIMEOUT_MS);
  const transforms = await getRuntimeTransforms(page);
  return {
    cycle,
    runtimeTransformCount: transforms.length,
  };
}

async function runMemoryCycles(page, suite, options, samples) {
  const cycleResults = [];
  for (let cycle = 1; cycle <= options.cycles; cycle += 1) {
    console.log(`\n── USD memory cycle ${cycle}/${options.cycles}: ${options.modelKey} ──`);
    const cycleResult = await runCycle(page, cycle, options.modelKey);
    cycleResults.push(cycleResult);
    samples.push(await sampleMemory(page, `cycle-${cycle}`));
    assertGreaterThan(
      suite,
      cycleResult.runtimeTransformCount,
      0,
      `cycle ${cycle}: runtime transforms present`,
    );
  }
  return cycleResults;
}

function getMaxPendingMetric(samples, metricName) {
  return Math.max(
    0,
    ...samples.flatMap((sample) =>
      sample.frames.map((frame) => Number(frame[metricName]?.pending ?? 0))),
  );
}

function summarizeMemorySamples(samples) {
  const warmup = samples[1] ?? samples[0];
  const final = samples[samples.length - 1];
  return {
    heapGrowthMb: Number((final.jsHeapUsedMb - warmup.jsHeapUsedMb).toFixed(2)),
    maxActiveWorkerTargets: Math.max(
      ...samples.map((sample) => Number(sample.activeWorkerTargetCount || 0)),
    ),
    finalActiveWorkerTargets: Number(final.activeWorkerTargetCount || 0),
    maxTrackedLiveWorkers: Math.max(...samples.map((sample) => sample.workerStats.maxLive || 0)),
    finalTrackedLiveWorkers: final.workerStats.live || 0,
    maxTexturePending: getMaxPendingMetric(samples, 'textureMetrics'),
    maxLoadingPending: getMaxPendingMetric(samples, 'loadingManagerMetrics'),
  };
}

function assertMemorySummary(suite, summary, options) {
  assert(
    suite,
    summary.heapGrowthMb <= options.maxHeapGrowthMb,
    `heap growth after warmup <= ${options.maxHeapGrowthMb} MB (${summary.heapGrowthMb} MB)`,
  );
  assert(
    suite,
    summary.maxTrackedLiveWorkers <= options.maxLiveWorkers,
    `tracked live workers <= ${options.maxLiveWorkers} `
      + `(max ${summary.maxTrackedLiveWorkers}, final ${summary.finalTrackedLiveWorkers})`,
  );
  assert(
    suite,
    summary.maxTexturePending === 0,
    `texture load pending returns to zero (${summary.maxTexturePending})`,
  );
  assert(
    suite,
    summary.maxLoadingPending === 0,
    `loading manager pending returns to zero (${summary.maxLoadingPending})`,
  );
}

async function writeMemoryReport(options, summary, cycleResults, samples, session) {
  await writeReport('usd_worker_memory_leak', {
    options,
    summary,
    cycleResults,
    samples,
    browserErrors: session.errors(),
  });
}

async function main() {
  const { help, options } = parseOptions(process.argv.slice(2));
  if (help) {
    printHelp();
    return;
  }

  const suite = createTestSuite('USD Worker Memory Leak');
  const session = await createSession();
  const samples = [];

  try {
    await installLeakProbe(session.page);
    samples.push(await sampleMemory(session.page, 'baseline'));

    const cycleResults = await runMemoryCycles(session.page, suite, options, samples);
    const summary = summarizeMemorySamples(samples);
    assertMemorySummary(suite, summary, options);
    await writeMemoryReport(options, summary, cycleResults, samples, session);
  } finally {
    await session.cleanup();
  }

  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
