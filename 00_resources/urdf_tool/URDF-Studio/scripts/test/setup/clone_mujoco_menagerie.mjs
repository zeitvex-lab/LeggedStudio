#!/usr/bin/env node

/**
 * Clone the MuJoCo menagerie corpus used by MJCF browser/fixture regression.
 * Target dir name keeps the GitHub "Download ZIP" convention (`<repo>-<branch>`).
 * Override the source with MUJOCO_MENAGERIE_URL if you maintain a mirror.
 */

import { cloneRepo, finishSingle } from './_clone-util.mjs';

const result = await cloneRepo({
  label: 'MuJoCo menagerie',
  url: process.env.MUJOCO_MENAGERIE_URL ?? 'https://github.com/google-deepmind/mujoco_menagerie.git',
  targetDir: 'test/mujoco_menagerie-main',
  branch: 'main',
});

finishSingle(result);
