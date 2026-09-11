#!/usr/bin/env node

/**
 * Unified "run everything" entry point — the one command for a full sweep.
 *
 * Stages (each can be toggled):
 *   1. unit     — Node unit tests via run-node-tests.mjs (default suite: all)
 *   2. browser  — every scripts/test/browser/test_*.mjs, auto-discovered from
 *                 package.json `test:browser:*` scripts (minus the `all` alias)
 *   3. fixtures — opt-in golden/truth fixture regression (needs large corpora)
 *
 * Design choices that make a full sweep practical:
 *   - Failures do NOT abort the run; every stage is attempted and the exit code
 *     reflects whether anything failed (CI-style).
 *   - One shared dev server is started up front on the default site URL. Each
 *     browser test's ensureSite() finds it reachable and reuses it instead of
 *     cold-starting its own Vite — turning N cold starts into one.
 *   - A consolidated pass/fail table is printed and written to
 *     tmp/regression/run-all-summary.json.
 *   - Browser automation is always cleaned up at the end (cleanup-headless.cjs).
 *
 * Usage:
 *   node scripts/test/runner/run-all.mjs [options]
 *     --unit-only            Run only the unit stage
 *     --browser-only         Run only the browser stage
 *     --skip-unit            Skip the unit stage
 *     --skip-browser         Skip the browser stage
 *     --fixtures             Include the (heavy) fixtures stage
 *     --unit-suite <name>    Unit suite to run (default: all)
 *     --headed               Run browser tests headed
 *     --filter <substr>      Only browser tests whose npm key includes <substr>
 *     --list                 List the resolved stages/commands and exit
 *     --help
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { ensureSite, DEFAULT_SITE_URL, writeJsonAtomic } from '../helpers/browser-helpers.mjs';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const SUMMARY_PATH = path.resolve(REPO_ROOT, 'tmp/regression/run-all-summary.json');
const CLEANUP_SCRIPT = 'test/usd-viewer/scripts/cleanup-headless.cjs';

function parseArgs(argv) {
  const opts = {
    unit: true,
    browser: true,
    fixtures: false,
    unitSuite: 'all',
    headed: false,
    filter: null,
    list: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case '--unit-only': opts.browser = false; opts.fixtures = false; break;
      case '--browser-only': opts.unit = false; opts.fixtures = false; break;
      case '--skip-unit': opts.unit = false; break;
      case '--skip-browser': opts.browser = false; break;
      case '--fixtures': opts.fixtures = true; break;
      case '--headed': opts.headed = true; break;
      case '--unit-suite': opts.unitSuite = argv[(i += 1)]; break;
      case '--filter': opts.filter = argv[(i += 1)]; break;
      case '--list': opts.list = true; break;
      case '--help': case '-h': opts.help = true; break;
      default: throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return opts;
}

function readPackageScripts() {
  const pkg = JSON.parse(fs.readFileSync(path.resolve(REPO_ROOT, 'package.json'), 'utf8'));
  return pkg.scripts ?? {};
}

/** Discover `test:browser:*` npm keys, excluding the `all` aggregate. */
function discoverBrowserKeys(scripts, filter) {
  return Object.keys(scripts)
    .filter((key) => key.startsWith('test:browser:') && key !== 'test:browser:all')
    .filter((key) => key !== 'test:browser:editor-deep-all')
    .filter((key) => (filter ? key.includes(filter) : true))
    .sort();
}

/** Discover `test:fixtures:*` npm keys, excluding aggregate/benchmark-heavy ones. */
function discoverFixtureKeys(scripts) {
  return Object.keys(scripts)
    .filter((key) => key.startsWith('test:fixtures:') && key !== 'test:fixtures')
    .filter((key) => !key.includes('benchmark') && !key.includes('isaacsim') && !key.includes('performance'))
    .sort();
}

function buildStages(opts, scripts) {
  /** @type {Array<{ stage: string, name: string, run: () => number }>} */
  const stages = [];

  if (opts.unit) {
    stages.push({
      stage: 'unit',
      name: `unit:${opts.unitSuite}`,
      run: () => spawnSync(
        process.execPath,
        ['scripts/test/runner/run-node-tests.mjs', opts.unitSuite],
        { cwd: REPO_ROOT, stdio: 'inherit' },
      ).status ?? 1,
    });
  }

  if (opts.browser) {
    for (const key of discoverBrowserKeys(scripts, opts.filter)) {
      stages.push({
        stage: 'browser',
        name: key,
        run: () => spawnSync('npm', ['run', key], {
          cwd: REPO_ROOT,
          stdio: 'inherit',
          env: { ...process.env, ...(opts.headed ? { URDF_E2E_HEADED: '1' } : {}) },
        }).status ?? 1,
      });
    }
  }

  if (opts.fixtures) {
    for (const key of discoverFixtureKeys(scripts)) {
      stages.push({
        stage: 'fixtures',
        name: key,
        run: () => spawnSync('npm', ['run', key], { cwd: REPO_ROOT, stdio: 'inherit' }).status ?? 1,
      });
    }
  }

  return stages;
}

function runCleanup() {
  if (!fs.existsSync(path.resolve(REPO_ROOT, CLEANUP_SCRIPT))) return;
  console.log(`\n[run-all] cleaning up headless browsers (${CLEANUP_SCRIPT})`);
  spawnSync(process.execPath, [CLEANUP_SCRIPT], { cwd: REPO_ROOT, stdio: 'inherit' });
}

function printTable(results) {
  const pad = (s, n) => String(s).padEnd(n);
  const nameWidth = Math.max(20, ...results.map((r) => r.name.length));
  console.log(`\n${'='.repeat(nameWidth + 26)}`);
  console.log(`${pad('TEST', nameWidth)}  ${pad('STAGE', 9)}  ${pad('RESULT', 7)}  TIME`);
  console.log('-'.repeat(nameWidth + 26));
  for (const r of results) {
    const mark = r.exitCode === 0 ? 'PASS' : 'FAIL';
    console.log(`${pad(r.name, nameWidth)}  ${pad(r.stage, 9)}  ${pad(mark, 7)}  ${(r.ms / 1000).toFixed(1)}s`);
  }
  console.log('='.repeat(nameWidth + 26));
  const passed = results.filter((r) => r.exitCode === 0).length;
  const failed = results.length - passed;
  console.log(`[run-all] total: ${results.length}, passed: ${passed}, failed: ${failed}`);
  if (failed > 0) {
    console.log(`[run-all] failed: ${results.filter((r) => r.exitCode !== 0).map((r) => r.name).join(', ')}`);
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(2, 38).join('\n'));
    return 0;
  }

  const scripts = readPackageScripts();
  const stages = buildStages(opts, scripts);

  if (stages.length === 0) {
    console.error('[run-all] no stages selected.');
    return 1;
  }

  if (opts.list) {
    console.log('[run-all] resolved stages:');
    for (const s of stages) console.log(`  ${s.stage.padEnd(9)} ${s.name}`);
    return 0;
  }

  const needsBrowser = stages.some((s) => s.stage === 'browser');
  let sharedSite = null;
  if (needsBrowser) {
    // Start one shared dev server so each browser test reuses it via ensureSite,
    // instead of cold-starting Vite N times.
    const siteUrl = new URL(DEFAULT_SITE_URL);
    siteUrl.searchParams.set('regressionDebug', '1');
    console.log(`[run-all] ensuring shared dev server at ${DEFAULT_SITE_URL} …`);
    try {
      sharedSite = await ensureSite(siteUrl.toString(), { siteTimeoutMs: 180_000 });
      console.log(`[run-all] shared server ready (started by run-all: ${sharedSite.startedByScript}).`);
    } catch (error) {
      console.error(`[run-all] could not start shared server: ${error.message}`);
      console.error('[run-all] browser tests will each start their own server.');
    }
  }

  const results = [];
  try {
    for (const stage of stages) {
      console.log(`\n──────── [${stage.stage}] ${stage.name} ────────`);
      const start = Date.now();
      let exitCode;
      try {
        exitCode = stage.run();
      } catch (error) {
        console.error(`[run-all] ${stage.name} threw: ${error.message}`);
        exitCode = 1;
      }
      results.push({ stage: stage.stage, name: stage.name, exitCode, ms: Date.now() - start });
    }
  } finally {
    if (sharedSite?.startedByScript) {
      console.log('[run-all] stopping shared dev server …');
      await sharedSite.stop();
    }
    if (needsBrowser) runCleanup();
  }

  await writeJsonAtomic(SUMMARY_PATH, {
    options: { unitSuite: opts.unitSuite, browser: opts.browser, fixtures: opts.fixtures, headed: opts.headed },
    results,
  });
  printTable(results);
  console.log(`[run-all] summary written to ${path.relative(REPO_ROOT, SUMMARY_PATH)}`);

  return results.some((r) => r.exitCode !== 0) ? 1 : 0;
}

main()
  .then((code) => { process.exitCode = code; })
  .catch((error) => { console.error(error); process.exitCode = 1; });
