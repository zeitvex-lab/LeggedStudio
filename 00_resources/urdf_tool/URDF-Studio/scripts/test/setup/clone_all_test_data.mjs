#!/usr/bin/env node

/**
 * Clone every large test-data corpus needed by the browser/fixture regression
 * suites. Idempotent — each already-present corpus is skipped. Failures are
 * collected and reported together (one missing corpus does not abort the rest).
 *
 * Note: the SDF (test/gazebo_models) and USDA (test/unitree_ros_usda) corpora are
 * not auto-cloned here because they have no single canonical git source; fetch
 * them manually if a suite reports them missing.
 */

import { cloneRepo } from './_clone-util.mjs';

const CORPORA = [
  {
    label: 'MuJoCo menagerie',
    url: process.env.MUJOCO_MENAGERIE_URL ?? 'https://github.com/google-deepmind/mujoco_menagerie.git',
    targetDir: 'test/mujoco_menagerie-main',
    branch: 'main',
  },
  {
    label: 'Unitree ROS URDF descriptions',
    url: process.env.UNITREE_ROS_URL ?? 'https://github.com/unitreerobotics/unitree_ros.git',
    targetDir: 'test/unitree_ros',
  },
  {
    label: 'Unitree USD model dataset',
    url: process.env.UNITREE_MODEL_URL ?? 'https://huggingface.co/datasets/unitreerobotics/unitree_model',
    targetDir: 'test/unitree_model',
  },
];

const results = [];
for (const corpus of CORPORA) {
  // Sequential on purpose: large clones should not contend for bandwidth/disk.
  // eslint-disable-next-line no-await-in-loop
  results.push(await cloneRepo(corpus));
}

const failed = results.filter((r) => r.status === 'failed');
const cloned = results.filter((r) => r.status === 'cloned');
const skipped = results.filter((r) => r.status === 'skipped');

console.log(
  `\n[setup] done — cloned: ${cloned.length}, skipped: ${skipped.length}, failed: ${failed.length}`,
);
if (failed.length > 0) {
  console.error(`[setup] failed corpora: ${failed.map((r) => r.label).join(', ')}`);
  process.exitCode = 1;
}
