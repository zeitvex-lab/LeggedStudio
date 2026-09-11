#!/usr/bin/env node

import path from 'node:path';

import { main } from './run_unitree_browser_regression.mjs';

main({
  defaultOutputPath: path.resolve('tmp/regression/unitree-ros-usda-selected.json'),
  scriptName: 'run_unitree_ros_usda_browser_regression.mjs',
}).catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
