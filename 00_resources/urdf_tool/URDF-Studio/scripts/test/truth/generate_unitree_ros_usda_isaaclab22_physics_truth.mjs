#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const DEFAULT_MANIFEST_PATH = path.resolve('test/unitree_ros_usda/export-manifest.json');
export const DEFAULT_OUTPUT_PATH = path.resolve(
  'tmp/regression/unitree-ros-usda-isaaclab22-physics.json',
);
export const DEFAULT_ISAACLAB_ROOT = path.resolve(
  '/home/xiangyk/Project/IsaacLab_Family/IsaacLab22/IsaacLab',
);
export const DEFAULT_ISAAC_PYTHON = path.resolve(
  '/home/xiangyk/anaconda3/envs/isaaclab22/bin/python',
);
const PHYSICS_INSPECTOR_PATH = path.resolve(
  'scripts/tools/isaacsim/inspect_isaacsim_physics_properties.py',
);

function printUsage() {
  console.log(`Usage:
  node scripts/test/truth/generate_unitree_ros_usda_isaaclab22_physics_truth.mjs [options]

Options:
  --manifest <path>       Unitree ROS USDA export manifest. Default: ${DEFAULT_MANIFEST_PATH}
  --output <path>         Physics truth JSON output. Default: ${DEFAULT_OUTPUT_PATH}
  --isaac-python <path>   IsaacLab/IsaacSim Python executable. Default: ${DEFAULT_ISAAC_PYTHON}
  --isaaclab-root <path>  IsaacLab root added to PYTHONPATH. Default: ${DEFAULT_ISAACLAB_ROOT}
  --model <filter>        Restrict to manifest output_usda paths containing a token. Repeatable.
  --limit <count>         Limit the number of stages after filtering.
  --help                  Show this help message.
`);
}

function parseArgs(argv) {
  const options = {
    help: false,
    isaacLabRoot: DEFAULT_ISAACLAB_ROOT,
    isaacPython: DEFAULT_ISAAC_PYTHON,
    limit: null,
    manifestPath: DEFAULT_MANIFEST_PATH,
    modelFilters: [],
    outputPath: DEFAULT_OUTPUT_PATH,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) {
        throw new Error(`Missing value for ${arg}`);
      }
      return argv[index];
    };

    switch (arg) {
      case '--manifest':
        options.manifestPath = path.resolve(next());
        break;
      case '--output':
        options.outputPath = path.resolve(next());
        break;
      case '--isaac-python':
        options.isaacPython = path.resolve(next());
        break;
      case '--isaaclab-root':
        options.isaacLabRoot = path.resolve(next());
        break;
      case '--model':
        options.modelFilters.push(next());
        break;
      case '--limit':
        options.limit = Number.parseInt(next(), 10);
        break;
      case '--help':
      case '-h':
        options.help = true;
        break;
      default:
        throw new Error(`Unknown option: ${arg}`);
    }
  }

  if (options.limit != null && (!Number.isInteger(options.limit) || options.limit < 1)) {
    throw new Error(`Invalid --limit: ${options.limit}`);
  }

  return options;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

function selectStagePaths(manifest, options) {
  const filters = options.modelFilters.map((entry) => String(entry).replace(/\\/g, '/'));
  const stagePaths = [];

  for (const record of manifest.records || []) {
    if (record?.status && record.status !== 'ok') {
      continue;
    }
    const outputUsda = String(record?.output_usda || '').replace(/\\/g, '/');
    if (!outputUsda) {
      continue;
    }
    if (filters.length > 0 && !filters.some((filter) => outputUsda.includes(filter))) {
      continue;
    }
    stagePaths.push(outputUsda);
  }

  return options.limit == null ? stagePaths : stagePaths.slice(0, options.limit);
}

function runProcess(command, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env,
      stdio: 'inherit',
    });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} ${args.join(' ')} exited with code ${code}`));
    });
  });
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printUsage();
    return;
  }

  const manifest = await readJson(options.manifestPath);
  const stagePaths = selectStagePaths(manifest, options);
  if (stagePaths.length === 0) {
    throw new Error(`No USDA stages matched ${options.manifestPath}`);
  }

  await fs.mkdir(path.dirname(options.outputPath), { recursive: true });
  await runProcess(
    options.isaacPython,
    [PHYSICS_INSPECTOR_PATH, ...stagePaths, '--output', options.outputPath, '--headless'],
    {
      ...process.env,
      PYTHONPATH: options.isaacLabRoot,
    },
  );

  const truth = await readJson(options.outputPath);
  const openedCount = Object.values(truth).filter((entry) => entry?.open_ok === true).length;
  const bodyCount = Object.values(truth).reduce(
    (total, entry) => total + Object.keys(entry?.rigidBodies || {}).length,
    0,
  );
  const jointCount = Object.values(truth).reduce(
    (total, entry) => total + Object.keys(entry?.joints || entry?.physicsJoints || {}).length,
    0,
  );

  console.log(
    JSON.stringify(
      {
        output: options.outputPath,
        stageCount: stagePaths.length,
        openedCount,
        rigidBodyCount: bodyCount,
        jointCount,
      },
      null,
      2,
    ),
  );
}

const isCli = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isCli) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : error);
    process.exitCode = 1;
  });
}
