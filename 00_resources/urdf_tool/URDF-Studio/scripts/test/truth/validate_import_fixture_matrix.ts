import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';

import {
  buildFixtureMatrix,
  DATASET_NAMES,
  installDomGlobals,
  parseCliArgs,
  writeReport,
  type DatasetName,
  type FixtureSummary,
} from './importFixtureMatrixShared';

const execFileAsync = promisify(execFile);
const SCRIPT_PATH = path.resolve('scripts/test/truth/validate_import_fixture_matrix.ts');

function filterSummaries(
  summaries: FixtureSummary[],
  matches: string[],
  limit: number | null,
): FixtureSummary[] {
  const normalizedMatches = matches.map((match) => match.trim().toLowerCase()).filter(Boolean);
  const filtered = normalizedMatches.length
    ? summaries.filter((row) => {
        const haystack = [
          row.id,
          row.dataset,
          row.supportRoot,
          row.entryPath,
          row.relativePath,
          row.classification,
          row.actualStatus,
        ]
          .join('\n')
          .toLowerCase();
        return normalizedMatches.every((match) => haystack.includes(match));
      })
    : summaries;

  return limit == null ? filtered : filtered.slice(0, limit);
}

async function runDatasetSubprocess(dataset: DatasetName): Promise<FixtureSummary[]> {
  const tempDir = await mkdtemp(path.join(os.tmpdir(), 'fixture-matrix-'));
  const outputPath = path.join(tempDir, `${dataset}.json`);

  try {
    await execFileAsync('npx', ['tsx', SCRIPT_PATH, '--dataset', dataset, '--output', outputPath], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        MATRIX_CHILD_RUN: '1',
      },
      maxBuffer: 1024 * 1024 * 8,
    });

    const report = JSON.parse(await readFile(outputPath, 'utf8')) as {
      summaries?: FixtureSummary[];
    };
    return Array.isArray(report.summaries) ? report.summaries : [];
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

async function main() {
  const { outputPath, datasets, matches, limit } = parseCliArgs(process.argv.slice(2));

  const summaries =
    datasets.length === 1
      ? (installDomGlobals(),
        await buildFixtureMatrix({
          datasets,
          matches,
          limit,
        }))
      : filterSummaries(
          (
            await DATASET_NAMES.reduce<Promise<FixtureSummary[]>>(async (pending, dataset) => {
              const collected = await pending;
              if (!datasets.includes(dataset)) {
                return collected;
              }
              return collected.concat(await runDatasetSubprocess(dataset));
            }, Promise.resolve([]))
          ).sort((left, right) => left.id.localeCompare(right.id)),
          matches,
          limit,
        );

  const report = await writeReport(outputPath, summaries);
  if (!process.env.MATRIX_CHILD_RUN) {
    console.log(JSON.stringify(report, null, 2));
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
