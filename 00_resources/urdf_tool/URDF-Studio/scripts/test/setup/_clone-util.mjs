#!/usr/bin/env node

/**
 * Shared helper for the test-data clone scripts.
 *
 * Each large fixture corpus (MuJoCo menagerie, Unitree URDF, Unitree USD …) lives
 * under test/ but is gitignored — too big to commit. These helpers fetch them on
 * demand and are idempotent: if the target already exists and is non-empty, the
 * clone is skipped. Source URLs can be overridden via env vars for mirrors.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';

export const REPO_ROOT = process.cwd();

async function isNonEmptyDir(dir) {
  try {
    const entries = await fs.readdir(dir);
    return entries.filter((name) => name !== '.git').length > 0;
  } catch {
    return false;
  }
}

/**
 * Clone (or skip) a repository into a target directory.
 * @param {object} spec
 * @param {string} spec.label        - Human-readable corpus name for logs.
 * @param {string} spec.url          - Git remote URL.
 * @param {string} spec.targetDir    - Destination relative to repo root (e.g. 'test/unitree_ros').
 * @param {string} [spec.branch]     - Optional branch to check out.
 * @param {number} [spec.depth=1]    - Shallow clone depth (0 = full history).
 * @returns {Promise<{ label: string, targetDir: string, status: 'skipped'|'cloned'|'failed', error?: string }>}
 */
export async function cloneRepo({ label, url, targetDir, branch, depth = 1 }) {
  const absTarget = path.resolve(REPO_ROOT, targetDir);

  if (await isNonEmptyDir(absTarget)) {
    console.log(`[setup] ✓ ${label}: already present at ${targetDir} — skipping`);
    return { label, targetDir, status: 'skipped' };
  }

  console.log(`[setup] ↓ ${label}: cloning ${url} → ${targetDir}`);
  await fs.mkdir(path.dirname(absTarget), { recursive: true });

  const args = ['clone'];
  if (depth > 0) args.push('--depth', String(depth));
  if (branch) args.push('--branch', branch);
  args.push(url, absTarget);

  const result = spawnSync('git', args, { stdio: 'inherit' });
  if (result.status !== 0) {
    const error = `git clone exited with code ${result.status ?? 'null'} (${result.error?.message ?? 'see output above'})`;
    console.error(`[setup] ✗ ${label}: ${error}`);
    return { label, targetDir, status: 'failed', error };
  }

  console.log(`[setup] ✓ ${label}: cloned into ${targetDir}`);
  return { label, targetDir, status: 'cloned' };
}

/** Map a result to a process exit code and print a one-line summary. */
export function finishSingle(result) {
  process.exitCode = result.status === 'failed' ? 1 : 0;
}
