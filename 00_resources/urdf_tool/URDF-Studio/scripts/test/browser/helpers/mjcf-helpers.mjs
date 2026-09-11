#!/usr/bin/env node

/**
 * Shared helpers for MuJoCo menagerie browser tests.
 * Wraps e2e browser-helpers with MJCF-specific import convenience.
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

const MENAGERIE = path.resolve('test/mujoco_menagerie-main');

// ── Import ───────────────────────────────────────────────────────────

export async function importModel(page, modelDir, fileName, timeoutMs = 60_000) {
  const dir = path.isAbsolute(modelDir) ? modelDir : path.join(MENAGERIE, modelDir);
  return importZippedModel(page, dir, fileName, timeoutMs, 'mjcf');
}
