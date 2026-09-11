#!/usr/bin/env node

/**
 * URDF-specific browser regression helpers.
 * Provides zip-bundle import for URDF robot packages.
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
  measureInteractionFrames, measureCanvasContinuityDuring, getSemanticSnapshot, getMaterialSnapshot,
  openSourceEditor, getSourceEditorText, replaceSourceEditorText, saveSourceEditor,
  waitForRobotPredicate, assertNoBrowserErrors,
  findAvailableFile,
  store, writeReport,
} from './base-helpers.mjs';

const UNITREE_ROS = path.resolve('test/unitree_ros/robots');

// ── Import ───────────────────────────────────────────────────────────

/**
 * Import a URDF robot package by uploading a zip of its directory.
 * @param {import('puppeteer').Page} page
 * @param {string} modelDir - Relative to test/unitree_ros/robots/ or absolute
 * @param {string} fileName - Expected file name after load (e.g. 'a1.urdf')
 * @param {number} [timeoutMs=60_000]
 */
export async function importModel(page, modelDir, fileName, timeoutMs = 60_000) {
  const dir = path.isAbsolute(modelDir) ? modelDir : path.join(UNITREE_ROS, modelDir);
  return importZippedModel(page, dir, fileName, timeoutMs, 'urdf');
}
