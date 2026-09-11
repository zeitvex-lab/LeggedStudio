import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';

import { JSDOM } from 'jsdom';

import { generateURDF } from '../../../src/core/parsers/urdf/urdfGenerator.ts';
import { parseURDF } from '../../../src/core/parsers/urdf/parser/index.ts';

const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/unitree-ros-urdfs.json');
const FIXTURE_ROOT = path.resolve('test/unitree_ros/robots');
const ROS_CANDIDATE_DIRS = ['humble', 'iron', 'jazzy', 'rolling'];

type Options = {
  modelFilters: string[];
  outputPath: string;
};

type CommandResult = {
  code: number;
  stderr: string;
  stdout: string;
};

type ValidationSummary = {
  generatedPath: string;
  generatedUrdfCheck: CommandResult;
  jointCount: number;
  linkCount: number;
  model: string;
  rosSetup: string;
  sourcePath: string;
  sourceUrdfCheck: CommandResult;
};

function installDomParser(): void {
  if (typeof DOMParser !== 'undefined') {
    return;
  }

  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    contentType: 'text/html',
  });
  globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
}

function fail(message: string): never {
  throw new Error(message);
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    modelFilters: [],
    outputPath: DEFAULT_OUTPUT_PATH,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (value == null) {
        fail(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--model':
        options.modelFilters.push(nextValue());
        break;
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--help':
      case '-h':
        process.stdout.write(`Usage:
  npx tsx scripts/test/truth/validate_unitree_ros_urdfs.ts [options]

Options:
  --model <path-token>   Restrict to default fixture paths matching this token. Repeatable.
  --output <path>        JSON summary path. Default: ${DEFAULT_OUTPUT_PATH}
  --help                 Show this help.
`);
        process.exit(0);
        return options;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

async function runCommand(command: string, args: string[]): Promise<CommandResult> {
  return await new Promise<CommandResult>((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on('data', (chunk) => {
      stderr += String(chunk);
    });
    child.on('error', reject);
    child.on('close', (code) => {
      resolve({
        code: code ?? 1,
        stdout,
        stderr,
      });
    });
  });
}

async function resolveRosSetupScript(): Promise<string> {
  for (const distro of ROS_CANDIDATE_DIRS) {
    const setupPath = path.join('/opt/ros', distro, 'setup.bash');
    try {
      await fs.access(setupPath);
    } catch {
      continue;
    }

    const probe = await runCommand('bash', [
      '-lc',
      `source ${JSON.stringify(setupPath)} && command -v check_urdf`,
    ]);
    if (probe.code === 0 && probe.stdout.trim().length > 0) {
      return setupPath;
    }
  }

  fail('Could not find a ROS setup.bash that provides check_urdf under /opt/ros.');
}

async function runCheckUrdf(filePath: string, rosSetup: string): Promise<CommandResult> {
  return await runCommand('bash', [
    '-lc',
    `source ${JSON.stringify(rosSetup)} && check_urdf ${JSON.stringify(filePath)}`,
  ]);
}

async function collectUrdfFiles(rootDir: string): Promise<string[]> {
  const entries = await fs.readdir(rootDir, { withFileTypes: true });
  const results: string[] = [];

  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      results.push(...(await collectUrdfFiles(absolutePath)));
      continue;
    }

    if (
      entry.isFile() &&
      entry.name.toLowerCase().endsWith('.urdf') &&
      absolutePath.includes(`${path.sep}urdf${path.sep}`)
    ) {
      results.push(absolutePath);
    }
  }

  return results;
}

async function discoverDefaultModels(): Promise<string[]> {
  const discovered = await collectUrdfFiles(FIXTURE_ROOT);
  return discovered
    .map((absolutePath) => path.relative(FIXTURE_ROOT, absolutePath).replace(/\\/g, '/'))
    .sort((left, right) => left.localeCompare(right));
}

function selectModels(models: string[], modelFilters: string[]): string[] {
  if (modelFilters.length === 0) {
    return models;
  }

  return models.filter((model) => modelFilters.some((filter) => model.includes(filter)));
}

async function validateModel(model: string, rosSetup: string, outputRoot: string): Promise<ValidationSummary> {
  const sourcePath = path.join(FIXTURE_ROOT, model);
  const sourceText = await fs.readFile(sourcePath, 'utf8');
  const robot = parseURDF(sourceText);
  if (!robot) {
    fail(`Failed to parse URDF fixture: ${sourcePath}`);
  }

  const generatedUrdf = generateURDF(robot);
  const generatedPath = path.join(
    outputRoot,
    model.replaceAll('/', '__').replace(/\.urdf$/i, '.roundtrip.urdf'),
  );
  await fs.mkdir(path.dirname(generatedPath), { recursive: true });
  await fs.writeFile(generatedPath, generatedUrdf, 'utf8');

  const [sourceUrdfCheck, generatedUrdfCheck] = await Promise.all([
    runCheckUrdf(sourcePath, rosSetup),
    runCheckUrdf(generatedPath, rosSetup),
  ]);

  if (sourceUrdfCheck.code !== 0) {
    fail(
      `Source URDF failed check_urdf: ${sourcePath}\n${sourceUrdfCheck.stderr || sourceUrdfCheck.stdout}`,
    );
  }
  if (generatedUrdfCheck.code !== 0) {
    fail(
      `Roundtrip URDF failed check_urdf: ${generatedPath}\n${generatedUrdfCheck.stderr || generatedUrdfCheck.stdout}`,
    );
  }

  return {
    model,
    sourcePath,
    generatedPath,
    rosSetup,
    linkCount: Object.keys(robot.links).length,
    jointCount: Object.keys(robot.joints).length,
    sourceUrdfCheck,
    generatedUrdfCheck,
  };
}

async function main(): Promise<void> {
  installDomParser();

  const options = parseArgs(process.argv.slice(2));
  const selectedModels = selectModels(await discoverDefaultModels(), options.modelFilters);
  if (selectedModels.length === 0) {
    fail('No Unitree ROS URDF fixtures matched the requested filters.');
  }

  const rosSetup = await resolveRosSetupScript();
  const artifactRoot = path.join(path.dirname(options.outputPath), 'unitree-ros-urdf-roundtrip');
  await fs.mkdir(path.dirname(options.outputPath), { recursive: true });

  const results: ValidationSummary[] = [];
  for (const model of selectedModels) {
    results.push(await validateModel(model, rosSetup, artifactRoot));
  }

  const summary = {
    generatedAtUtc: new Date().toISOString(),
    rosSetup,
    modelCount: results.length,
    results,
  };

  await fs.writeFile(options.outputPath, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
