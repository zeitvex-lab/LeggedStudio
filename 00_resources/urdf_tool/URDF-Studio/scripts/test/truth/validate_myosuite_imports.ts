import path from 'node:path';

import {
  buildFixtureMatrix,
  installDomGlobals,
  parseCliArgs,
  writeReport,
} from './importFixtureMatrixShared';

const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/myosuite-import-matrix.json');

async function main() {
  installDomGlobals();
  const { outputPath, matches, limit } = parseCliArgs(process.argv.slice(2), DEFAULT_OUTPUT_PATH);
  const summaries = await buildFixtureMatrix({
    datasets: ['myosuite-main'],
    matches,
    limit,
  });
  const report = await writeReport(outputPath, summaries);
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
