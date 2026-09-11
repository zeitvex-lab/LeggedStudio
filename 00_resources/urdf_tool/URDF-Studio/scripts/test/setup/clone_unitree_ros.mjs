#!/usr/bin/env node

/**
 * Clone the Unitree ROS URDF descriptions used by URDF browser/fixture regression.
 * Override with UNITREE_ROS_URL if needed.
 */

import { cloneRepo, finishSingle } from './_clone-util.mjs';

const result = await cloneRepo({
  label: 'Unitree ROS URDF descriptions',
  url: process.env.UNITREE_ROS_URL ?? 'https://github.com/unitreerobotics/unitree_ros.git',
  targetDir: 'test/unitree_ros',
});

finishSingle(result);
