#!/usr/bin/env node

/**
 * Xacro-specific browser regression helpers.
 * Provides zip-bundle import for xacro packages.
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

const UNITREE_ROS = path.resolve('test/unitree_ros/robots');

// ── Import ───────────────────────────────────────────────────────────

/**
 * Import a xacro package by uploading a zip of the model directory.
 * @param {import('puppeteer').Page} page
 * @param {string} xacroPath - Absolute or relative path to the .xacro file
 * @param {string} expectedName - Expected name after expansion (e.g. 'robot.xacro')
 * @param {number} [timeoutMs=60_000]
 */
export async function importModel(page, xacroPath, expectedName, timeoutMs = 60_000) {
  const absPath = path.isAbsolute(xacroPath) ? xacroPath : path.join(UNITREE_ROS, xacroPath);
  const relativePath = path.relative(UNITREE_ROS, absPath);
  const [packageName] = relativePath.split(path.sep);
  const packageDir =
    packageName && !packageName.startsWith('..') && packageName !== relativePath
      ? path.join(UNITREE_ROS, packageName)
      : path.dirname(absPath);
  return importZippedModel(page, packageDir, expectedName, timeoutMs, 'xacro');
}
