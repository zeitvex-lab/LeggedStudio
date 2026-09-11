#!/usr/bin/env node

/**
 * SDF-specific browser regression helpers.
 * Provides zip-bundle import for Gazebo SDF model packages.
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

const GAZEBO_MODELS = path.resolve('test/gazebo_models');

// ── Import ───────────────────────────────────────────────────────────

/**
 * Import an SDF model by uploading a zip of its directory.
 * @param {import('puppeteer').Page} page
 * @param {string} modelDir - Relative to test/gazebo_models/ or absolute
 * @param {string} fileName - Expected file name after load (e.g. 'model.sdf')
 * @param {number} [timeoutMs=60_000]
 */
export async function importModel(page, modelDir, fileName, timeoutMs = 60_000) {
  const dir = path.isAbsolute(modelDir) ? modelDir : path.join(GAZEBO_MODELS, modelDir);
  const expectedName = fileName.includes('/') || fileName.includes('\\')
    ? fileName
    : `${path.basename(dir)}/${fileName}`;
  return importZippedModel(page, dir, expectedName, timeoutMs, 'sdf');
}
