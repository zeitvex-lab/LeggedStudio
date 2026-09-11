import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

interface Options {
  allowMissing: boolean;
  checkUrdfBin: string;
  datasetRoot: string;
  limit: number | null;
  matches: string[];
  outputPath: string;
  timeoutMs: number;
}

interface UrdfdomValidationResult {
  exitCode: number | null;
  relativePath: string;
  signal: NodeJS.Signals | null;
  status: 'pass' | 'fail' | 'skipped';
  stderr: string;
  stdout: string;
}

interface UrdfdomValidationReport {
  checkUrdf: {
    available: boolean;
    bin: string;
    missingReason: string | null;
  };
  datasetRoot: string;
  failCount: number;
  generatedAt: string;
  options: {
    limit: number | null;
    matches: string[];
    timeoutMs: number;
  };
  passCount: number;
  results: UrdfdomValidationResult[];
  selectedCount: number;
  skippedCount: number;
}

const DEFAULT_DATASET_ROOT = path.resolve('test/urdf_files_dataset');
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/urdf-files-urdfdom.json');
const DEFAULT_CHECK_URDF_BIN = process.env.CHECK_URDF_BIN || 'check_urdf';
const DEFAULT_TIMEOUT_MS = 15_000;
const MAX_CAPTURED_OUTPUT_LENGTH = 20_000;

function fail(message: string): never {
  throw new Error(message);
}

function normalizePath(filePath: string): string {
  return filePath.replace(/\\/g, '/');
}

function parsePositiveInteger(value: string, label: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1) {
    fail(`Invalid ${label}: ${value}`);
  }
  return parsed;
}

function printUsage(): void {
  process.stdout.write(`Usage:
  npx tsx scripts/test/truth/validate_urdf_files_dataset_against_urdfdom.ts [options]

Options:
  --dataset-root <path>       Dataset root. Default: ${DEFAULT_DATASET_ROOT}
  --output <path>             JSON report path. Default: ${DEFAULT_OUTPUT_PATH}
  --match <token>             Repeatable filter against relative path.
  --limit <n>                 Limit selected URDF files after filtering.
  --check-urdf-bin <path>     check_urdf executable. Default: ${DEFAULT_CHECK_URDF_BIN}
  --timeout-ms <n>            Per-file timeout. Default: ${DEFAULT_TIMEOUT_MS}
  --allow-missing             Write a skipped report when check_urdf is unavailable.
  --help                      Show this help.
`);
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    allowMissing: false,
    checkUrdfBin: DEFAULT_CHECK_URDF_BIN,
    datasetRoot: DEFAULT_DATASET_ROOT,
    limit: null,
    matches: [],
    outputPath: DEFAULT_OUTPUT_PATH,
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (!value) {
        fail(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--allow-missing':
        options.allowMissing = true;
        break;
      case '--check-urdf-bin':
        options.checkUrdfBin = nextValue();
        break;
      case '--dataset-root':
        options.datasetRoot = path.resolve(nextValue());
        break;
      case '--help':
      case '-h':
        printUsage();
        process.exit(0);
        break;
      case '--limit':
        options.limit = parsePositiveInteger(nextValue(), '--limit');
        break;
      case '--match':
      case '--model':
        options.matches.push(nextValue().trim().toLowerCase());
        break;
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--timeout-ms':
        options.timeoutMs = parsePositiveInteger(nextValue(), '--timeout-ms');
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

async function collectUrdfFiles(root: string): Promise<string[]> {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    const absolutePath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectUrdfFiles(absolutePath)));
      continue;
    }

    if (entry.isFile() && entry.name.toLowerCase().endsWith('.urdf')) {
      files.push(absolutePath);
    }
  }

  return files.sort((a, b) => normalizePath(a).localeCompare(normalizePath(b)));
}

function selectFiles(files: string[], datasetRoot: string, options: Options): string[] {
  const filtered = options.matches.length
    ? files.filter((filePath) => {
        const relativePath = normalizePath(path.relative(datasetRoot, filePath)).toLowerCase();
        return options.matches.every((match) => relativePath.includes(match));
      })
    : files;

  return options.limit ? filtered.slice(0, options.limit) : filtered;
}

function trimCapturedOutput(output: string): string {
  if (output.length <= MAX_CAPTURED_OUTPUT_LENGTH) {
    return output;
  }

  const truncatedLength = output.length - MAX_CAPTURED_OUTPUT_LENGTH;
  return `${output.slice(0, MAX_CAPTURED_OUTPUT_LENGTH)}\n[truncated ${truncatedLength} chars]`;
}

function runCheckUrdf(
  checkUrdfBin: string,
  filePath: string,
  timeoutMs: number,
): Promise<UrdfdomValidationResult> {
  return new Promise((resolve) => {
    const child = spawn(checkUrdfBin, [filePath], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    let settled = false;
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, timeoutMs);

    child.stdout.on('data', (chunk: Buffer) => stdoutChunks.push(chunk));
    child.stderr.on('data', (chunk: Buffer) => stderrChunks.push(chunk));

    child.on('error', (error: NodeJS.ErrnoException) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve({
        exitCode: null,
        relativePath: '',
        signal: null,
        status: 'fail',
        stderr: error.code === 'ENOENT' ? `check_urdf executable not found: ${checkUrdfBin}` : error.message,
        stdout: '',
      });
    });

    child.on('close', (exitCode, signal) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      const stdout = trimCapturedOutput(Buffer.concat(stdoutChunks).toString('utf8'));
      const stderr = trimCapturedOutput(Buffer.concat(stderrChunks).toString('utf8'));
      const failed = timedOut || exitCode !== 0;
      resolve({
        exitCode,
        relativePath: '',
        signal,
        status: failed ? 'fail' : 'pass',
        stderr: timedOut ? `${stderr}\nTimed out after ${timeoutMs}ms`.trim() : stderr,
        stdout,
      });
    });
  });
}

function createMissingToolResults(
  selectedFiles: string[],
  datasetRoot: string,
  reason: string,
): UrdfdomValidationResult[] {
  return selectedFiles.map((filePath) => ({
    exitCode: null,
    relativePath: normalizePath(path.relative(datasetRoot, filePath)),
    signal: null,
    status: 'skipped',
    stderr: reason,
    stdout: '',
  }));
}

async function writeReport(report: UrdfdomValidationReport, outputPath: string): Promise<void> {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const datasetRoot = path.resolve(options.datasetRoot);
  const allFiles = await collectUrdfFiles(datasetRoot);
  const selectedFiles = selectFiles(allFiles, datasetRoot, options);
  if (selectedFiles.length === 0) {
    fail('No URDF files matched the requested filters.');
  }

  const results: UrdfdomValidationResult[] = [];
  let checkUrdfAvailable = true;
  let missingReason: string | null = null;

  for (const filePath of selectedFiles) {
    const relativePath = normalizePath(path.relative(datasetRoot, filePath));
    const result = await runCheckUrdf(options.checkUrdfBin, filePath, options.timeoutMs);
    if (result.stderr.includes('check_urdf executable not found')) {
      checkUrdfAvailable = false;
      missingReason = result.stderr;
      break;
    }

    results.push({
      ...result,
      relativePath,
    });
  }

  const finalResults = checkUrdfAvailable
    ? results
    : createMissingToolResults(selectedFiles, datasetRoot, missingReason ?? 'check_urdf unavailable');

  const report: UrdfdomValidationReport = {
    checkUrdf: {
      available: checkUrdfAvailable,
      bin: options.checkUrdfBin,
      missingReason,
    },
    datasetRoot,
    failCount: finalResults.filter((result) => result.status === 'fail').length,
    generatedAt: new Date().toISOString(),
    options: {
      limit: options.limit,
      matches: options.matches,
      timeoutMs: options.timeoutMs,
    },
    passCount: finalResults.filter((result) => result.status === 'pass').length,
    results: finalResults,
    selectedCount: selectedFiles.length,
    skippedCount: finalResults.filter((result) => result.status === 'skipped').length,
  };

  await writeReport(report, options.outputPath);

  console.log(
    JSON.stringify(
      {
        outputPath: options.outputPath,
        selectedCount: report.selectedCount,
        passCount: report.passCount,
        failCount: report.failCount,
        skippedCount: report.skippedCount,
        checkUrdfAvailable,
      },
      null,
      2,
    ),
  );

  if (!checkUrdfAvailable && !options.allowMissing) {
    fail(
      `${missingReason}. Install urdfdom tools, for example apt package liburdfdom-tools, `
        + 'or pass --check-urdf-bin.',
    );
  }

  if (report.failCount > 0) {
    process.exitCode = 1;
  }
}

void main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
