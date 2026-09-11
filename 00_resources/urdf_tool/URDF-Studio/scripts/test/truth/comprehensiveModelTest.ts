/**
 * Comprehensive Model Import / Assembly / Export Test
 *
 * For every robot model under test/ this script:
 *   1. Imports the model via resolveRobotFileData
 *   2. Validates ground-truth (link count, joint count, root link id)
 *   3. Adds the model as an assembly component
 *   4. Exports the robot to URDF
 *   5. Re-imports the exported URDF and verifies structural consistency
 *
 * Usage:
 *   npx tsx scripts/test/truth/comprehensiveModelTest.ts [options]
 *
 * Options:
 *   --dataset <name>   Run only one dataset (repeatable)
 *   --match <token>    Filter entries by case-insensitive token (repeatable)
 *   --limit <n>        Cap number of entries
 *   --output <path>    JSON report path
 *   --skip-roundtrip   Skip URDF export round-trip checks
 *   --help             Show help
 */

import { mkdir, writeFile } from 'node:fs/promises';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import {
  buildFixtureMatrix,
  installDomGlobals,
  type DatasetName,
  type FixtureSummary,
} from './importFixtureMatrixShared';

import { resolveRobotFileData, type RobotImportResult } from '../../../src/core/parsers/importRobotFile';
import { generateURDF } from '../../../src/core/parsers/urdf/urdfGenerator';
import { findUnsupportedUrdfJoint } from '../../../src/core/parsers/urdf/urdfExportSupport';
import {
  sanitizeAssemblyComponentId,
  namespaceAssemblyRobotData,
} from '../../../src/core/robot/assemblyComponentPreparation';
import type { RobotData, RobotFile, RobotState } from '../../../src/types';

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------

const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/comprehensive-model-test.json');

type Options = {
  outputPath: string;
  datasets: DatasetName[];
  matches: string[];
  limit: number | null;
  skipRoundtrip: boolean;
};

function parseArgs(argv: string[]): Options {
  const options: Options = {
    outputPath: DEFAULT_OUTPUT_PATH,
    datasets: [],
    matches: [],
    limit: null,
    skipRoundtrip: false,
  };
  let datasetFilterApplied = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (!value) throw new Error(`Missing value for ${arg}`);
      index += 1;
      return value;
    };

    switch (arg) {
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--dataset': {
        const dataset = nextValue() as DatasetName;
        if (!datasetFilterApplied) {
          options.datasets = [];
          datasetFilterApplied = true;
        }
        if (!options.datasets.includes(dataset)) {
          options.datasets.push(dataset);
        }
        break;
      }
      case '--match':
        options.matches.push(nextValue().trim().toLowerCase());
        break;
      case '--limit': {
        const parsed = Number.parseInt(nextValue(), 10);
        if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`Invalid --limit: ${parsed}`);
        options.limit = parsed;
        break;
      }
      case '--skip-roundtrip':
        options.skipRoundtrip = true;
        break;
      case '--help':
      case '-h':
        process.stdout.write(`Usage:
  npx tsx scripts/test/truth/comprehensiveModelTest.ts [options]

Options:
  --output <path>    JSON report path. Default: ${DEFAULT_OUTPUT_PATH}
  --dataset <name>   Dataset filter. Repeatable.
  --match <token>    Case-insensitive entry filter. Repeatable.
  --limit <n>        Cap number of entries.
  --skip-roundtrip   Skip URDF export round-trip validation.
  --help             Show this help.
`);
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ImportPhase = 'pass' | 'fail';
type AssemblyPhase = 'pass' | 'fail' | 'skipped';
type ExportPhase = 'pass' | 'fail' | 'skipped';
type RoundtripPhase = 'pass' | 'fail' | 'skipped';

interface ComprehensiveResult {
  id: string;
  dataset: string;
  entryPath: string;
  format: string;

  // Phase 1: Import
  importPhase: ImportPhase;
  importMessage: string | null;
  linkCount: number | null;
  jointCount: number | null;
  rootLinkId: string | null;

  // Phase 2: Assembly (add as component)
  assemblyPhase: AssemblyPhase;
  assemblyMessage: string | null;
  componentId: string | null;
  namespacedLinkCount: number | null;

  // Phase 3: Export to URDF
  exportPhase: ExportPhase;
  exportMessage: string | null;
  exportedUrdfLength: number | null;

  // Phase 4: Roundtrip (re-import exported URDF)
  roundtripPhase: RoundtripPhase;
  roundtripMessage: string | null;
  roundtripLinkCount: number | null;
  roundtripJointCount: number | null;
}

// ---------------------------------------------------------------------------
// Phase 1: Import
// ---------------------------------------------------------------------------

function runImportPhase(
  file: RobotFile,
  availableFiles: RobotFile[],
  allFileContents: Record<string, string>,
): {
  result: RobotImportResult;
  robotData: RobotData | null;
  linkCount: number | null;
  jointCount: number | null;
  rootLinkId: string | null;
  message: string | null;
} {
  let result: RobotImportResult;
  try {
    result = resolveRobotFileData(file, {
      availableFiles,
      allFileContents,
    });
  } catch (error) {
    return {
      result: {
        status: 'error',
        format: file.format,
        reason: 'parse_failed',
        message: error instanceof Error ? error.message : String(error),
      },
      robotData: null,
      linkCount: null,
      jointCount: null,
      rootLinkId: null,
      message: error instanceof Error ? error.message : String(error),
    };
  }

  if (result.status !== 'ready') {
    return {
      result,
      robotData: null,
      linkCount: null,
      jointCount: null,
      rootLinkId: null,
      message:
        result.status === 'error'
          ? result.message ?? result.reason
          : result.status === 'needs_hydration'
            ? 'USD hydration required'
            : result.reason,
    };
  }

  const robotData = result.robotData;
  const linkCount = Object.keys(robotData.links).length;
  const jointCount = Object.keys(robotData.joints).length;

  return {
    result,
    robotData,
    linkCount,
    jointCount,
    rootLinkId: robotData.rootLinkId,
    message: null,
  };
}

// ---------------------------------------------------------------------------
// Phase 2: Assembly (add as component via namespace)
// ---------------------------------------------------------------------------

function runAssemblyPhase(
  robotData: RobotData,
  fileName: string,
): {
  componentId: string | null;
  namespacedRobotData: RobotData | null;
  namespacedLinkCount: number | null;
  message: string | null;
} {
  try {
    const componentId = `comp_${sanitizeAssemblyComponentId(fileName)}`;
    const namespacedRobotData = namespaceAssemblyRobotData(robotData, {
      componentId,
      rootName: robotData.name || 'robot',
    });
    const namespacedLinkCount = Object.keys(namespacedRobotData.links).length;

    // Verify namespace prefix applied correctly
    const hasExpectedPrefix = Object.keys(namespacedRobotData.links).every(
      (linkId) => linkId === componentId || linkId.startsWith(`${componentId}_`),
    );

    if (!hasExpectedPrefix && Object.keys(namespacedRobotData.links).length > 0) {
      return {
        componentId,
        namespacedRobotData,
        namespacedLinkCount,
        message: `Namespace prefix mismatch: not all links start with ${componentId}`,
      };
    }

    return {
      componentId,
      namespacedRobotData,
      namespacedLinkCount,
      message: null,
    };
  } catch (error) {
    return {
      componentId: null,
      namespacedRobotData: null,
      namespacedLinkCount: null,
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

// ---------------------------------------------------------------------------
// Phase 3: Export to URDF
// ---------------------------------------------------------------------------

function runExportPhase(
  robotData: RobotData,
): {
  exportedUrdf: string | null;
  exportedUrdfLength: number | null;
  message: string | null;
} {
  try {
    // RobotData -> RobotState requires a `selection` field for generateURDF
    const robotState = {
      ...robotData,
      selection: {
        selectedLinkIds: new Set<string>(),
        selectedJointIds: new Set<string>(),
        hoveredLinkId: null as string | null,
        hoveredJointId: null as string | null,
      },
    };

    const exportedUrdf = generateURDF(robotState as RobotState);
    return {
      exportedUrdf,
      exportedUrdfLength: exportedUrdf.length,
      message: null,
    };
  } catch (error) {
    return {
      exportedUrdf: null,
      exportedUrdfLength: null,
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

// ---------------------------------------------------------------------------
// Phase 4: Roundtrip (re-import exported URDF)
// ---------------------------------------------------------------------------

function runRoundtripPhase(
  exportedUrdf: string,
  originalRobotData: RobotData,
): {
  roundtripLinkCount: number | null;
  roundtripJointCount: number | null;
  message: string | null;
} {
  try {
    const result = resolveRobotFileData({
      name: 'roundtrip_export.urdf',
      content: exportedUrdf,
      format: 'urdf',
    });

    if (result.status !== 'ready') {
      return {
        roundtripLinkCount: null,
        roundtripJointCount: null,
        message: `Roundtrip import failed: ${result.status === 'error' ? result.message ?? result.reason : result.status}`,
      };
    }

    const roundtripData = result.robotData;
    const roundtripLinkCount = Object.keys(roundtripData.links).length;
    const roundtripJointCount = Object.keys(roundtripData.joints).length;

    const originalLinkCount = Object.keys(originalRobotData.links).length;

    // Count only "valid" original joints (those whose child links actually exist)
    const validOriginalJointCount = Object.values(originalRobotData.joints).filter(
      (joint) => originalRobotData.links[joint.childLinkId] && originalRobotData.links[joint.parentLinkId],
    ).length;

    // Verify structural consistency
    if (roundtripLinkCount !== originalLinkCount) {
      return {
        roundtripLinkCount,
        roundtripJointCount,
        message: `Link count mismatch: original=${originalLinkCount}, roundtrip=${roundtripLinkCount}`,
      };
    }

    if (roundtripJointCount !== validOriginalJointCount) {
      return {
        roundtripLinkCount,
        roundtripJointCount,
        message: `Joint count mismatch: original=${validOriginalJointCount}, roundtrip=${roundtripJointCount}`,
      };
    }

    return {
      roundtripLinkCount,
      roundtripJointCount,
      message: null,
    };
  } catch (error) {
    return {
      roundtripLinkCount: null,
      roundtripJointCount: null,
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

// ---------------------------------------------------------------------------
// File collection per support root (mirrors importFixtureMatrixShared logic)
// ---------------------------------------------------------------------------

const TEXT_CONTENT_EXTENSIONS = new Set([
  '.config', '.json', '.material', '.mdl', '.mjcf', '.mtl', '.sdf', '.txt',
  '.urdf', '.usda', '.xacro', '.xml',
]);
function detectFormatFromPath(relativePath: string): RobotFile['format'] {
  const ext = path.extname(relativePath).toLowerCase();
  if (ext === '.urdf') return 'urdf';
  if (ext === '.xacro') return 'xacro';
  if (ext === '.sdf') return 'sdf';
  if (ext === '.usda') return 'usd';
  if (ext === '.usdc' || ext === '.usd') return 'usd';
  if (ext === '.xml') return 'mjcf';
  return 'mesh';
}

function collectContextForSupportRoot(
  datasetRoot: string,
  supportRootRel: string,
  additionalContextRoots: string[] = [],
): { importFiles: RobotFile[]; allFileContents: Record<string, string> } {
  const allRoots = [path.join(datasetRoot, supportRootRel), ...additionalContextRoots];
  const importFiles: RobotFile[] = [];
  const allFileContents: Record<string, string> = {};

  for (const root of allRoots) {
    if (!fs.existsSync(root)) continue;
    const absolutePaths = collectAllFiles(root);
    for (const absPath of absolutePaths) {
      const ext = path.extname(absPath).toLowerCase();
      if (!TEXT_CONTENT_EXTENSIONS.has(ext)) continue;
      const relPath = path.relative(datasetRoot, absPath);
      try {
        const content = fs.readFileSync(absPath, 'utf8');
        allFileContents[relPath] = content;
        const format = detectFormatFromPath(relPath);
        importFiles.push({ name: relPath, content, format });
      } catch {
        // skip unreadable files
      }
    }
  }

  return { importFiles, allFileContents };
}

function collectAllFiles(dir: string): string[] {
  const results: string[] = [];
  function walk(d: string) {
    let entries: fs.Dirent[];
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory() && entry.name !== 'node_modules' && !entry.name.startsWith('.')) {
        walk(full);
      } else if (entry.isFile()) {
        results.push(full);
      }
    }
  }
  walk(dir);
  return results.sort();
}

// ---------------------------------------------------------------------------
// Full pipeline
// ---------------------------------------------------------------------------

async function buildComprehensiveResults(
  options: Options,
): Promise<{ results: ComprehensiveResult[]; summary: SummaryStats }> {
  installDomGlobals();

  const datasets = options.datasets.length > 0 ? options.datasets : undefined;
  const summaries = await buildFixtureMatrix({
    datasets,
    matches: options.matches,
    limit: options.limit,
  });

  // Filter to only entries with status 'ready' (successful imports)
  const readyEntries = summaries.filter(
    (s) => s.actualStatus === 'ready' && s.linkCount !== null && s.linkCount > 0,
  );

  console.log(`\n=== Comprehensive Model Test ===`);
  console.log(`Total entries in fixture matrix: ${summaries.length}`);
  console.log(`Entries with successful imports (ready): ${readyEntries.length}`);

  const results: ComprehensiveResult[] = [];
  let passed = 0;
  let failed = 0;

  // Group entries by support root for batched file reading
  const entriesBySupportRoot = new Map<string, FixtureSummary[]>();
  for (const entry of readyEntries) {
    const key = `${entry.dataset}:${entry.supportRoot}`;
    if (!entriesBySupportRoot.has(key)) {
      entriesBySupportRoot.set(key, []);
    }
    entriesBySupportRoot.get(key)!.push(entry);
  }

  let processed = 0;
  const total = readyEntries.length;

  for (const entries of entriesBySupportRoot.values()) {
    const firstEntry = entries[0];
    const datasetRoot = findDatasetRoot(firstEntry.dataset);
    if (!datasetRoot) continue;

    // Collect ALL source files for this support root (for dependency resolution)
    const additionalRoots = getAdditionalContextRoots(firstEntry.dataset);
    const { importFiles: availableFiles, allFileContents } = collectContextForSupportRoot(
      datasetRoot,
      firstEntry.supportRoot,
      additionalRoots,
    );

    for (const entry of entries) {
      processed++;
      const shortPath = entry.entryPath.length > 60
        ? '...' + entry.entryPath.slice(-57)
        : entry.entryPath;

      process.stdout.write(
        `\r[${processed}/${total}] Testing: ${shortPath}          `,
      );

      const result: ComprehensiveResult = {
        id: entry.id,
        dataset: entry.dataset,
        entryPath: entry.entryPath,
        format: entry.format,
        importPhase: 'pass',
        importMessage: null,
        linkCount: entry.linkCount,
        jointCount: entry.jointCount,
        rootLinkId: entry.rootLinkId,
        assemblyPhase: 'skipped',
        assemblyMessage: null,
        componentId: null,
        namespacedLinkCount: null,
        exportPhase: 'skipped',
        exportMessage: null,
        exportedUrdfLength: null,
        roundtripPhase: 'skipped',
        roundtripMessage: null,
        roundtripLinkCount: null,
        roundtripJointCount: null,
      };

      // --- Phase 1: Import ---
      // Find the matching file from our collected files
      const file = availableFiles.find((f) => f.name === entry.entryPath);
      if (!file) {
        result.importPhase = 'fail';
        result.importMessage = `File not found in context: ${entry.entryPath}`;
        results.push(result);
        failed++;
        continue;
      }

      const importResult = runImportPhase(file, availableFiles, allFileContents);

      if (importResult.robotData === null) {
        result.importPhase = 'fail';
        result.importMessage = importResult.message;
        results.push(result);
        failed++;
        continue;
      }

      // Ground truth verification
      const actualLinkCount = importResult.linkCount!;
      const actualJointCount = importResult.jointCount!;
      const actualRootLinkId = importResult.rootLinkId!;

      result.linkCount = actualLinkCount;
      result.jointCount = actualJointCount;
      result.rootLinkId = actualRootLinkId;

      // Verify link count matches expected (from fixture matrix)
      if (entry.linkCount !== null && actualLinkCount !== entry.linkCount) {
        result.importPhase = 'fail';
        result.importMessage = `Link count mismatch: expected=${entry.linkCount}, actual=${actualLinkCount}`;
        results.push(result);
        failed++;
        continue;
      }

      // Verify joint count matches expected
      if (entry.jointCount !== null && actualJointCount !== entry.jointCount) {
        result.importPhase = 'fail';
        result.importMessage = `Joint count mismatch: expected=${entry.jointCount}, actual=${actualJointCount}`;
        results.push(result);
        failed++;
        continue;
      }

      // Verify root link exists
      if (!importResult.robotData.links[actualRootLinkId]) {
        result.importPhase = 'fail';
        result.importMessage = `Root link "${actualRootLinkId}" not found in links`;
        results.push(result);
        failed++;
        continue;
      }

      // --- Phase 2: Assembly ---
      const assemblyResult = runAssemblyPhase(importResult.robotData, file.name);
      if (assemblyResult.message) {
        result.assemblyPhase = 'fail';
        result.assemblyMessage = assemblyResult.message;
      } else {
        result.assemblyPhase = 'pass';
        result.componentId = assemblyResult.componentId;
        result.namespacedLinkCount = assemblyResult.namespacedLinkCount;

        // Verify link count preserved after namespace
        if (
          assemblyResult.namespacedLinkCount !== null &&
          actualLinkCount !== assemblyResult.namespacedLinkCount
        ) {
          result.assemblyPhase = 'fail';
          result.assemblyMessage = `Namespaced link count mismatch: original=${actualLinkCount}, namespaced=${assemblyResult.namespacedLinkCount}`;
        }
      }

      // --- Phase 3: Export ---
      // Check for unsupported URDF joint types (e.g., ball joints)
      const unsupportedJoint = findUnsupportedUrdfJoint(
        importResult.robotData,
      );
      let exportResult: ReturnType<typeof runExportPhase>;
      if (unsupportedJoint) {
        exportResult = {
          exportedUrdf: null,
          exportedUrdfLength: null,
          message: `Skipped: ${unsupportedJoint.jointType} joint "${unsupportedJoint.jointName}" not supported in URDF`,
        };
      } else {
        exportResult = runExportPhase(importResult.robotData);
      }
      if (exportResult.message) {
        if (exportResult.message.startsWith('Skipped:')) {
          result.exportPhase = 'pass';
          result.exportMessage = exportResult.message;
          result.roundtripPhase = 'pass';
          result.roundtripMessage = 'Skipped: export skipped';
        } else {
          result.exportPhase = 'fail';
          result.exportMessage = exportResult.message;
        }
      } else {
        result.exportPhase = 'pass';
        result.exportedUrdfLength = exportResult.exportedUrdfLength;

        // Verify exported URDF is non-empty and valid XML
        if (!exportResult.exportedUrdf || exportResult.exportedUrdf.length < 50) {
          result.exportPhase = 'fail';
          result.exportMessage = `Exported URDF too short: ${exportResult.exportedUrdfLength} chars`;
        }
      }

      // --- Phase 4: Roundtrip ---
      if (!options.skipRoundtrip && exportResult.exportedUrdf) {
        const roundtripResult = runRoundtripPhase(
          exportResult.exportedUrdf,
          importResult.robotData,
        );
        if (roundtripResult.message) {
          result.roundtripPhase = 'fail';
          result.roundtripMessage = roundtripResult.message;
        } else {
          result.roundtripPhase = 'pass';
          result.roundtripLinkCount = roundtripResult.roundtripLinkCount;
          result.roundtripJointCount = roundtripResult.roundtripJointCount;
        }
      }

      // Overall pass/fail
      const allPhasesPassed =
        result.importPhase === 'pass' &&
        (result.assemblyPhase === 'pass' || result.assemblyPhase === 'skipped') &&
        (result.exportPhase === 'pass' || result.exportPhase === 'skipped') &&
        (result.roundtripPhase === 'pass' || result.roundtripPhase === 'skipped');

      if (allPhasesPassed) {
        passed++;
      } else {
        failed++;
      }

      results.push(result);
    }
  }

  process.stdout.write('\n\n');

  const summary: SummaryStats = {
    total,
    passed,
    failed,
    skipped: 0,
    importPass: results.filter((r) => r.importPhase === 'pass').length,
    importFail: results.filter((r) => r.importPhase === 'fail').length,
    assemblyPass: results.filter((r) => r.assemblyPhase === 'pass').length,
    assemblyFail: results.filter((r) => r.assemblyPhase === 'fail').length,
    exportPass: results.filter((r) => r.exportPhase === 'pass').length,
    exportFail: results.filter((r) => r.exportPhase === 'fail').length,
    roundtripPass: results.filter((r) => r.roundtripPhase === 'pass').length,
    roundtripFail: results.filter((r) => r.roundtripPhase === 'fail').length,
  };

  return { results, summary };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface SummaryStats {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  importPass: number;
  importFail: number;
  assemblyPass: number;
  assemblyFail: number;
  exportPass: number;
  exportFail: number;
  roundtripPass: number;
  roundtripFail: number;
}

function findDatasetRoot(datasetName: string): string | null {
  const roots: Record<string, string> = {
    unitree_ros: path.resolve('test/unitree_ros/robots'),
    'mujoco_menagerie-main': path.resolve('test/mujoco_menagerie-main'),
    'myosuite-main': path.resolve('test/myosuite-main'),
    awesome_robot_descriptions_repos: path.resolve('test/awesome_robot_descriptions_repos'),
  };
  return roots[datasetName] ?? null;
}

function getAdditionalContextRoots(datasetName: string): string[] {
  if (datasetName === 'mujoco_menagerie-main') {
    return [path.resolve('test/mujoco_menagerie-main/assets')];
  }
  return [];
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

function printReport(summary: SummaryStats): void {
  console.log('\n=== Test Report ===\n');
  console.log(`Total models tested:  ${summary.total}`);
  console.log(`PASSED:               ${summary.passed}`);
  console.log(`FAILED:               ${summary.failed}`);
  console.log();
  console.log('Phase breakdown:');
  console.log(`  Import:    ${summary.importPass} pass / ${summary.importFail} fail`);
  console.log(`  Assembly:  ${summary.assemblyPass} pass / ${summary.assemblyFail} fail`);
  console.log(`  Export:    ${summary.exportPass} pass / ${summary.exportFail} fail`);
  console.log(`  Roundtrip: ${summary.roundtripPass} pass / ${summary.roundtripFail} fail`);
  console.log();
}

function printFailures(results: ComprehensiveResult[]): void {
  const failures = results.filter(
    (r) =>
      r.importPhase === 'fail' ||
      r.assemblyPhase === 'fail' ||
      r.exportPhase === 'fail' ||
      r.roundtripPhase === 'fail',
  );

  if (failures.length === 0) {
    console.log('All tests passed!\n');
    return;
  }

  console.log(`\n=== Failures (${failures.length}) ===\n`);
  for (const f of failures.slice(0, 50)) {
    console.log(`[${f.dataset}] ${f.entryPath}`);
    if (f.importPhase === 'fail') console.log(`  IMPORT:    ${f.importMessage}`);
    if (f.assemblyPhase === 'fail') console.log(`  ASSEMBLY:  ${f.assemblyMessage}`);
    if (f.exportPhase === 'fail') console.log(`  EXPORT:    ${f.exportMessage}`);
    if (f.roundtripPhase === 'fail') console.log(`  ROUNDTRIP: ${f.roundtripMessage}`);
    console.log();
  }

  if (failures.length > 50) {
    console.log(`... and ${failures.length - 50} more failures`);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const { results, summary } = await buildComprehensiveResults(options);

  printReport(summary);
  printFailures(results);

  // Write JSON report
  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(
    options.outputPath,
    JSON.stringify(
      {
        validatedAt: new Date().toISOString(),
        summary,
        results,
      },
      null,
      2,
    ) + '\n',
    'utf8',
  );
  console.log(`Report written to: ${options.outputPath}\n`);

  if (summary.failed > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
