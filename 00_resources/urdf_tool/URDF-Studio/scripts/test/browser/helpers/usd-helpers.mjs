#!/usr/bin/env node

/**
 * USD/USDA-specific browser regression helpers.
 * Provides seed-and-load import for USD and USDA model files,
 * using the regression debug API (seedFixtureFile + loadRobotByName).
 */

import path from 'node:path';

import { importZippedModel } from './zip-import-helpers.mjs';

// Re-export all format-agnostic helpers
export {
  createTestSuite, assert, assertEqual, assertGreaterThan, assertNonNull, printSummary,
  DEFAULT_OPERATION_TIMEOUT_MS,
  createSession, waitForReady, getTopology, getAssemblyState, getRuntimeTransforms,
  getRegressionSnapshot, getProjectedInteractionTargets, getBestProjectedInteractionTarget,
  getCanvasDiagnostics, clickCanvasTarget, dragCanvasByDelta, measureCanvasDrag,
  measureInteractionFrames, getSemanticSnapshot, getMaterialSnapshot,
  openSourceEditor, getSourceEditorText, replaceSourceEditorText, saveSourceEditor,
  waitForRobotPredicate, assertNoBrowserErrors,
  findAvailableFile,
  store, writeReport,
} from './base-helpers.mjs';

// ── Import ───────────────────────────────────────────────────────────

/**
 * Seed fixture files from a directory and load a specific USD/USDA model.
 * @param {import('puppeteer').Page} page
 * @param {object} options
 * @param {string} options.sourceRoot - Absolute path to model root directory
 * @param {string} options.exposedRoot - Relative path under public test dir
 * @param {string} options.loadFileName - File name to load via debug API
 * @param {number} [options.timeoutMs=120_000]
 */
export async function importModel(page, { sourceRoot, exposedRoot, loadFileName }, timeoutMs = 120_000) {
  void exposedRoot;
  return importZippedModel(page, sourceRoot, loadFileName, timeoutMs, 'usd');
}

/**
 * Convenience: import a Unitree USD model by key name.
 * @param {import('puppeteer').Page} page
 * @param {string} modelKey - e.g. 'Go2', 'H1', 'B2'
 * @param {number} [timeoutMs=120_000]
 */
export async function importUnitreeModel(page, modelKey, timeoutMs = 120_000) {
  const UNITREE_MODELS = {
    Go2: {
      sourceRoot: path.resolve('test/unitree_model/Go2'),
      exposedRoot: 'unitree_model/Go2',
      loadFileName: 'usd/go2.usd',
    },
    Go2W: {
      sourceRoot: path.resolve('test/unitree_model/Go2W'),
      exposedRoot: 'unitree_model/Go2W',
      loadFileName: 'usd/go2w.usd',
    },
    B2: {
      sourceRoot: path.resolve('test/unitree_model/B2'),
      exposedRoot: 'unitree_model/B2',
      loadFileName: 'usd/b2.usd',
    },
    H1: {
      sourceRoot: path.resolve('test/unitree_model/H1/h1'),
      exposedRoot: 'unitree_model/H1/h1',
      loadFileName: 'usd/h1.usd',
    },
  };

  const config = UNITREE_MODELS[modelKey];
  if (!config) {
    throw new Error(`Unknown Unitree model key: ${modelKey}. Available: ${Object.keys(UNITREE_MODELS).join(', ')}`);
  }

  return importModel(page, config, timeoutMs);
}
