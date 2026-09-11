import assert from 'node:assert/strict';
import { access, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { JSDOM } from 'jsdom';

import { pickPreferredImportFile } from '@/app/hooks/importPreferredFile';
import { detectImportFormat } from '@/app/utils/import-preparation/formatDetection';
import {
  isStandaloneXacroEntry,
  resolveRobotFileData,
  type RobotImportResult,
} from '@/core/parsers/importRobotFile';
import {
  isLikelyNonRenderableUsdConfigPath,
  pickPreferredUsdRootFile,
} from '@/core/parsers/usd/usdFormatUtils';
import type { RobotFile } from '@/types';

export const DATASET_NAMES = [
  'unitree_ros',
  'mujoco_menagerie-main',
  'myosuite-main',
  'unitree_ros_usda',
  'unitree_model',
  'awesome_robot_descriptions_repos',
] as const;

export type DatasetName = (typeof DATASET_NAMES)[number];
export type ValidationMode = 'standalone_import' | 'dependency_validation';
export type FixtureStatus =
  | 'ready'
  | 'parse_failed'
  | 'source_only_fragment'
  | 'unsupported_format'
  | 'needs_hydration'
  | 'classification_only';
export type FixtureClassification =
  | 'preferred_entry'
  | 'importable_source'
  | 'source_fragment'
  | 'parse_failed'
  | 'usd_root'
  | 'usd_dependency_layer';

export interface FixtureSummary {
  id: string;
  kind: string;
  relativePath: string;
  status: FixtureStatus;
  linkCount: number | null;
  jointCount: number | null;
  rootLinkId: string | null;
  dataset: DatasetName;
  supportRoot: string;
  entryPath: string;
  format: string;
  validationMode: ValidationMode;
  classification: FixtureClassification;
  expectedStatus: FixtureStatus;
  actualStatus: FixtureStatus;
  pass: boolean;
  resultStatus: 'pass' | 'partial' | 'fail';
  message: string | null;
}

export interface FixtureReport {
  validatedAt: string;
  sampleCount: number;
  passCount: number;
  partialCount: number;
  failCount: number;
  summaries: FixtureSummary[];
}

export interface CliOptions {
  outputPath: string;
  datasets: DatasetName[];
  matches: string[];
  limit: number | null;
}

export interface ExpectedSourceOverride {
  classification: FixtureClassification;
  expectedStatus: Exclude<FixtureStatus, 'classification_only' | 'needs_hydration'>;
  validationMode: ValidationMode;
  message?: string;
}

interface DatasetDefinition {
  name: DatasetName;
  absoluteRoot: string;
  sourceMode: 'source' | 'usd';
  sourceSelection?: 'all' | 'preferred_only';
  discoverSupportRoots: () => Promise<string[]>;
  getAdditionalContextRoots?: (supportRootAbs: string) => string[];
}

interface SourceContext {
  dataset: DatasetDefinition;
  supportRootAbs: string;
  supportRoot: string;
  importFiles: RobotFile[];
  allFileContents: Record<string, string>;
  preferredFileName: string | null;
}

const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/fixture-import-matrix.json');
const TEXT_CONTENT_EXTENSIONS = new Set([
  '.config',
  '.json',
  '.material',
  '.mdl',
  '.mjcf',
  '.mtl',
  '.sdf',
  '.txt',
  '.urdf',
  '.usda',
  '.xacro',
  '.xml',
]);
const USD_EXTENSIONS = new Set(['.usd', '.usda', '.usdc', '.usdz']);
const SOURCE_EXTENSIONS = new Set(['.mjcf', '.sdf', '.urdf', '.xacro', '.xml']);
const TEMPLATE_PLACEHOLDER_TOKENS = ['OBJECT_NAME'] as const;
const AWESOME_ROBOT_EXPECTED_OVERRIDES = new Map<string, ExpectedSourceOverride>([
  [
    'aero-hand-open/sim_rl/mujoco_playground/mujoco_playground/_src/dm_control_suite/xmls/common/materials.xml',
    {
      classification: 'source_fragment',
      expectedStatus: 'source_only_fragment',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'aero-hand-open/sim_rl/mujoco_playground/mujoco_playground/_src/manipulation/franka_emika_panda/xmls/mjx_cabinet.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'bullet3/data/reduced_beam/reduced_beam.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'bullet3/data/reduced_cube/deform_cube.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'bullet3/data/reduced_torus/reduced_torus.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'ergocub-software/urdf/ergoCub/conf/ergocub.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'halodi-robot-models/halodi-robot-models-unity-support/Packages/halodi-robot-models/Runtime/Halodi/Models/qb_hand_description/dummy.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'halodi-robot-models/qb_hand_description/dummy.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'icub-models/iCub/conf/icub.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'icub-models/iCub_creo2urdf/conf_creo2urdf/icub.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'icub-models/iCub_manual/conf_manual/iCubGazeboV2_5_visuomanip/icub.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'icub-models/iCub_manual/ros/transform-server.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'models/pr2_description/urdf/pr2_simplified.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'roboschool/roboschool/models_robot/fetch_description/robots/fetch.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'robot-assets/urdfs/robots/fetch/robots/fetch.urdf',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
  [
    'unitree_mujoco/terrain_tool/scene.xml',
    {
      classification: 'parse_failed',
      expectedStatus: 'parse_failed',
      validationMode: 'dependency_validation',
    },
  ],
]);
const DATASET_DEFINITIONS: Record<DatasetName, DatasetDefinition> = {
  unitree_ros: {
    name: 'unitree_ros',
    absoluteRoot: path.resolve('test/unitree_ros/robots'),
    sourceMode: 'source',
    sourceSelection: 'all',
    discoverSupportRoots: async () => listImmediateChildDirs(path.resolve('test/unitree_ros/robots')),
  },
  'mujoco_menagerie-main': {
    name: 'mujoco_menagerie-main',
    absoluteRoot: path.resolve('test/mujoco_menagerie-main'),
    sourceMode: 'source',
    sourceSelection: 'all',
    discoverSupportRoots: async () =>
      listImmediateChildDirs(path.resolve('test/mujoco_menagerie-main'), {
        excludeDirNames: ['assets'],
      }),
    getAdditionalContextRoots: () => [path.resolve('test/mujoco_menagerie-main/assets')],
  },
  'myosuite-main': {
    name: 'myosuite-main',
    absoluteRoot: path.resolve('test/myosuite-main'),
    sourceMode: 'source',
    sourceSelection: 'all',
    discoverSupportRoots: async () => [path.resolve('test/myosuite-main')],
  },
  unitree_ros_usda: {
    name: 'unitree_ros_usda',
    absoluteRoot: path.resolve('test/unitree_ros_usda'),
    sourceMode: 'usd',
    discoverSupportRoots: async () => discoverUsdSupportRoots(path.resolve('test/unitree_ros_usda')),
  },
  unitree_model: {
    name: 'unitree_model',
    absoluteRoot: path.resolve('test/unitree_model'),
    sourceMode: 'usd',
    discoverSupportRoots: async () => discoverUsdSupportRoots(path.resolve('test/unitree_model')),
  },
  awesome_robot_descriptions_repos: {
    name: 'awesome_robot_descriptions_repos',
    absoluteRoot: path.resolve('test/awesome_robot_descriptions_repos'),
    sourceMode: 'source',
    sourceSelection: 'preferred_only',
    discoverSupportRoots: async () =>
      discoverSourceSupportRoots(path.resolve('test/awesome_robot_descriptions_repos')),
  },
};

export function installDomGlobals(): void {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { contentType: 'text/html' });
  globalThis.window = dom.window as typeof globalThis.window;
  globalThis.document = dom.window.document as typeof globalThis.document;
  globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
  globalThis.Node = dom.window.Node as typeof Node;
  globalThis.Element = dom.window.Element as typeof Element;
  globalThis.Document = dom.window.Document as typeof Document;
  globalThis.self = globalThis;
}

export function parseCliArgs(argv: string[], defaultOutputPath = DEFAULT_OUTPUT_PATH): CliOptions {
  const options: CliOptions = {
    outputPath: defaultOutputPath,
    datasets: [...DATASET_NAMES],
    matches: [],
    limit: null,
  };
  let datasetFilterApplied = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (!value) {
        throw new Error(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--dataset': {
        const dataset = nextValue() as DatasetName;
        if (!DATASET_NAMES.includes(dataset)) {
          throw new Error(`Unknown dataset: ${dataset}`);
        }
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
        if (!Number.isFinite(parsed) || parsed < 0) {
          throw new Error(`Invalid --limit value: ${parsed}`);
        }
        options.limit = parsed;
        break;
      }
      case '--help':
      case '-h':
        process.stdout.write(
          [
            'Usage: node <script> [options]',
            '',
            'Options:',
            `  --output <path>    JSON report path. Default: ${defaultOutputPath}`,
            `  --dataset <name>   Dataset filter. Repeatable. Supported: ${DATASET_NAMES.join(', ')}`,
            '  --match <token>    Case-insensitive entry filter. Repeatable.',
            '  --limit <n>        Cap the number of emitted rows after filtering.',
            '  --help             Show this help.',
            '',
          ].join('\n'),
        );
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

export async function writeReport(outputPath: string, summaries: FixtureSummary[]): Promise<FixtureReport> {
  const report: FixtureReport = {
    validatedAt: new Date().toISOString(),
    sampleCount: summaries.length,
    passCount: summaries.filter((entry) => entry.resultStatus === 'pass').length,
    partialCount: summaries.filter((entry) => entry.resultStatus === 'partial').length,
    failCount: summaries.filter((entry) => entry.resultStatus === 'fail').length,
    summaries,
  };
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  return report;
}

export async function buildFixtureMatrix(options: {
  datasets?: DatasetName[];
  matches?: string[];
  limit?: number | null;
} = {}): Promise<FixtureSummary[]> {
  const datasets = options.datasets?.length ? options.datasets : [...DATASET_NAMES];
  const rows: FixtureSummary[] = [];

  for (const datasetName of datasets) {
    const dataset = DATASET_DEFINITIONS[datasetName];
    const supportRoots = await dataset.discoverSupportRoots();
    for (const supportRootAbs of supportRoots) {
      if (dataset.sourceMode === 'usd') {
        rows.push(...(await buildUsdRows(dataset, supportRootAbs)));
        continue;
      }
      rows.push(...(await buildSourceRows(dataset, supportRootAbs)));
    }
  }

  return filterRows(rows, options.matches ?? [], options.limit ?? null);
}

function getKnownExpectedSourceOverride(
  datasetName: DatasetName,
  entryPath: string,
): ExpectedSourceOverride | undefined {
  if (datasetName !== 'awesome_robot_descriptions_repos') {
    return undefined;
  }
  return AWESOME_ROBOT_EXPECTED_OVERRIDES.get(normalizePath(entryPath));
}

export async function buildExplicitSourceRows(options: {
  dataset: DatasetName;
  supportRootAbs?: string;
  entryPaths: string[];
  overrides?: Record<string, ExpectedSourceOverride>;
}): Promise<FixtureSummary[]> {
  const dataset = DATASET_DEFINITIONS[options.dataset];
  assert.equal(dataset.sourceMode, 'source', `${options.dataset} must be a source dataset`);
  const supportRootAbs = options.supportRootAbs ?? dataset.absoluteRoot;
  const context = await createSourceContext(dataset, supportRootAbs);
  const rows = [] as FixtureSummary[];

  for (const entryPath of options.entryPaths) {
    const file = context.importFiles.find((candidate) => candidate.name === normalizePath(entryPath));
    if (!file) {
      rows.push(
        createSummaryRow({
          dataset: dataset.name,
          supportRoot: context.supportRoot,
          entryPath: normalizePath(entryPath),
          relativePath: toRepoRelative(path.join(dataset.absoluteRoot, entryPath)),
          format: 'unknown',
          validationMode: 'standalone_import',
          classification: 'parse_failed',
          expectedStatus: 'parse_failed',
          actualStatus: 'parse_failed',
          pass: false,
          message: `Missing fixture entry: ${entryPath}`,
        }),
      );
      continue;
    }
    rows.push(await validateSourceFile(context, file, options.overrides?.[file.name]));
  }

  return rows.sort(compareSummaries);
}

async function buildSourceRows(dataset: DatasetDefinition, supportRootAbs: string): Promise<FixtureSummary[]> {
  const context = await createSourceContext(dataset, supportRootAbs);
  const filesToValidate =
    dataset.sourceSelection === 'preferred_only' && context.preferredFileName
      ? context.importFiles.filter((file) => file.name === context.preferredFileName)
      : context.importFiles;
  const rows = [] as FixtureSummary[];
  for (const file of filesToValidate) {
    rows.push(await validateSourceFile(context, file));
  }
  return rows.sort(compareSummaries);
}

async function createSourceContext(
  dataset: DatasetDefinition,
  supportRootAbs: string,
): Promise<SourceContext> {
  const allContextRoots = [supportRootAbs, ...(dataset.getAdditionalContextRoots?.(supportRootAbs) ?? [])];
  const uniqueFiles = new Map<string, string>();

  for (const rootAbs of allContextRoots) {
    if (!(await pathExists(rootAbs))) {
      continue;
    }
    const absolutePaths = await collectFiles(rootAbs);
    for (const absolutePath of absolutePaths) {
      if (!isPotentialImportOrTextSupportFile(absolutePath)) {
        continue;
      }
      uniqueFiles.set(absolutePath, absolutePath);
    }
  }

  const textEntries = [] as Array<{ absolutePath: string; relativePath: string; content: string }>;
  const importFiles = [] as RobotFile[];

  for (const absolutePath of [...uniqueFiles.values()].sort((left, right) => left.localeCompare(right))) {
    const relativePath = toDatasetRelative(dataset.absoluteRoot, absolutePath);
    if (shouldReadAsText(absolutePath)) {
      const content = await readFile(absolutePath, 'utf8');
      textEntries.push({ absolutePath, relativePath, content });
      const format = detectFixtureFormat(relativePath, content);
      if (shouldValidateImportFile(format, content)) {
        importFiles.push({
          name: relativePath,
          content,
          format,
        });
      }
    }
  }

  const preferredFile = pickPreferredImportFile(importFiles, importFiles);

  return {
    dataset,
    supportRootAbs,
    supportRoot: toDatasetRelative(dataset.absoluteRoot, supportRootAbs) || '.',
    importFiles,
    allFileContents: Object.fromEntries(textEntries.map((entry) => [entry.relativePath, entry.content])),
    preferredFileName: preferredFile?.name ?? null,
  };
}

async function validateSourceFile(
  context: SourceContext,
  file: RobotFile,
  override?: ExpectedSourceOverride,
): Promise<FixtureSummary> {
  let result: RobotImportResult;
  try {
    result = withSuppressedImportNoise(() =>
      resolveRobotFileData(file, {
        availableFiles: context.importFiles,
        allFileContents: context.allFileContents,
      }),
    );
  } catch (error) {
    result = {
      status: 'error',
      format: file.format,
      reason: 'parse_failed',
      message: error instanceof Error ? error.message : String(error),
    };
  }

  const actualStatus = normalizeImportStatus(result);
  const derivedExpectation = deriveSourceExpectation({
    file,
    preferredFileName: context.preferredFileName,
    actualStatus,
    override: override ?? getKnownExpectedSourceOverride(context.dataset.name, file.name),
  });
  const legacy = extractLegacyCounts(result);

  return createSummaryRow({
    dataset: context.dataset.name,
    supportRoot: context.supportRoot,
    entryPath: file.name,
    relativePath: toRepoRelative(path.join(context.dataset.absoluteRoot, file.name)),
    format: file.format,
    validationMode: derivedExpectation.validationMode,
    classification: derivedExpectation.classification,
    expectedStatus: derivedExpectation.expectedStatus,
    actualStatus,
    pass: actualStatus === derivedExpectation.expectedStatus,
    message:
      override?.message ??
      (result.status === 'error' ? result.message ?? null : result.status === 'needs_hydration' ? 'USD hydration required' : null),
    linkCount: legacy.linkCount,
    jointCount: legacy.jointCount,
    rootLinkId: legacy.rootLinkId,
  });
}

function deriveSourceExpectation(options: {
  file: RobotFile;
  preferredFileName: string | null;
  actualStatus: FixtureStatus;
  override?: ExpectedSourceOverride;
}): ExpectedSourceOverride {
  if (options.override) {
    return options.override;
  }

  if (options.file.name === options.preferredFileName) {
    return {
      classification: 'preferred_entry',
      expectedStatus: 'ready',
      validationMode: 'standalone_import',
    };
  }

  if (options.file.format === 'xacro' && !isStandaloneXacroEntry(options.file)) {
    return {
      classification: 'source_fragment',
      expectedStatus: 'source_only_fragment',
      validationMode: 'dependency_validation',
    };
  }

  if (options.actualStatus === 'ready') {
    return {
      classification: 'importable_source',
      expectedStatus: 'ready',
      validationMode: 'standalone_import',
    };
  }

  if (options.actualStatus === 'source_only_fragment') {
    return {
      classification: 'source_fragment',
      expectedStatus: 'source_only_fragment',
      validationMode: 'dependency_validation',
    };
  }

  return {
    classification: 'parse_failed',
    expectedStatus: options.actualStatus === 'unsupported_format' ? 'unsupported_format' : 'parse_failed',
    validationMode: 'dependency_validation',
  };
}

async function buildUsdRows(dataset: DatasetDefinition, supportRootAbs: string): Promise<FixtureSummary[]> {
  const absolutePaths = await collectFiles(supportRootAbs);
  const usdFiles = absolutePaths
    .filter((absolutePath) => isUsdPath(absolutePath))
    .map((absolutePath) => ({
      absolutePath,
      name: toDatasetRelative(dataset.absoluteRoot, absolutePath),
    }))
    .sort((left, right) => left.name.localeCompare(right.name));

  if (usdFiles.length === 0) {
    return [];
  }

  const preferredRoot = pickPreferredUsdRootFile(usdFiles);
  const supportRoot = toDatasetRelative(dataset.absoluteRoot, supportRootAbs) || '.';
  const hasConfigLayers = usdFiles.some((file) => isUsdDependencyLayer(file.name));

  return usdFiles
    .map((file) => {
      const classification = isUsdDependencyLayer(file.name) ? 'usd_dependency_layer' : 'usd_root';
      const validationMode: ValidationMode =
        classification === 'usd_dependency_layer' ? 'dependency_validation' : 'standalone_import';
      const isPreferredRoot =
        classification === 'usd_root' && preferredRoot != null && preferredRoot.name === file.name;
      const pass =
        classification === 'usd_dependency_layer'
          ? true
          : preferredRoot != null && (isPreferredRoot || file.name.endsWith('.viewer_roundtrip.usd') || hasConfigLayers);

      return createSummaryRow({
        dataset: dataset.name,
        supportRoot,
        entryPath: file.name,
        relativePath: toRepoRelative(file.absolutePath),
        format: 'usd',
        validationMode,
        classification,
        expectedStatus: 'classification_only',
        actualStatus: 'classification_only',
        pass,
        message:
          classification === 'usd_dependency_layer'
            ? 'USD dependency/config layer'
            : isPreferredRoot
              ? 'Preferred USD root'
              : 'Additional standalone USD root',
      });
    })
    .sort(compareSummaries);
}

function normalizeImportStatus(result: RobotImportResult): FixtureStatus {
  if (result.status === 'ready') {
    return 'ready';
  }
  if (result.status === 'needs_hydration') {
    return 'needs_hydration';
  }
  return result.reason;
}

function withSuppressedImportNoise<T>(run: () => T): T {
  const originalError = console.error;
  const originalWarn = console.warn;
  const originalLog = console.log;

  console.error = () => {};
  console.warn = () => {};
  console.log = () => {};

  try {
    return run();
  } finally {
    console.error = originalError;
    console.warn = originalWarn;
    console.log = originalLog;
  }
}

function extractLegacyCounts(result: RobotImportResult): {
  linkCount: number | null;
  jointCount: number | null;
  rootLinkId: string | null;
} {
  if (result.status !== 'ready') {
    return {
      linkCount: null,
      jointCount: null,
      rootLinkId: null,
    };
  }

  return {
    linkCount: Object.keys(result.robotData.links).length,
    jointCount: Object.keys(result.robotData.joints).length,
    rootLinkId: result.robotData.rootLinkId ?? null,
  };
}

function createSummaryRow(input: {
  dataset: DatasetName;
  supportRoot: string;
  entryPath: string;
  relativePath: string;
  format: string;
  validationMode: ValidationMode;
  classification: FixtureClassification;
  expectedStatus: FixtureStatus;
  actualStatus: FixtureStatus;
  pass: boolean;
  message?: string | null;
  linkCount?: number | null;
  jointCount?: number | null;
  rootLinkId?: string | null;
}): FixtureSummary {
  return {
    id: `${input.dataset}:${input.entryPath}`,
    kind: input.format,
    relativePath: input.relativePath,
    status: input.actualStatus,
    linkCount: input.linkCount ?? null,
    jointCount: input.jointCount ?? null,
    rootLinkId: input.rootLinkId ?? null,
    dataset: input.dataset,
    supportRoot: input.supportRoot,
    entryPath: input.entryPath,
    format: input.format,
    validationMode: input.validationMode,
    classification: input.classification,
    expectedStatus: input.expectedStatus,
    actualStatus: input.actualStatus,
    pass: input.pass,
    resultStatus: input.pass ? 'pass' : 'fail',
    message: input.message ?? null,
  };
}

function filterRows(rows: FixtureSummary[], matches: string[], limit: number | null): FixtureSummary[] {
  const normalizedMatches = matches.map((match) => match.trim().toLowerCase()).filter(Boolean);
  const filtered = normalizedMatches.length
    ? rows.filter((row) => {
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
    : rows;

  return (limit == null ? filtered : filtered.slice(0, limit)).sort(compareSummaries);
}

function compareSummaries(left: FixtureSummary, right: FixtureSummary): number {
  if (left.dataset !== right.dataset) {
    return left.dataset.localeCompare(right.dataset);
  }
  if (left.supportRoot !== right.supportRoot) {
    return left.supportRoot.localeCompare(right.supportRoot);
  }
  return left.entryPath.localeCompare(right.entryPath);
}

function detectFixtureFormat(fileName: string, content: string): RobotFile['format'] | null {
  const extension = path.extname(fileName).toLowerCase();
  if (extension === '.urdf') return 'urdf';
  if (extension === '.sdf') return 'sdf';
  if (extension === '.mjcf') return 'mjcf';
  if (extension === '.xacro') return 'xacro';
  if (USD_EXTENSIONS.has(extension)) return 'usd';
  if (extension === '.xml') {
    const detected = detectImportFormat(content, fileName);
    if (detected === 'mjcf' || detected === 'sdf' || detected === 'urdf' || detected === 'xacro') {
      return detected;
    }
  }
  return null;
}

function hasTemplatePlaceholder(content: string): boolean {
  return TEMPLATE_PLACEHOLDER_TOKENS.some((token) => content.includes(token));
}

function isPotentialImportOrTextSupportFile(absolutePath: string): boolean {
  const extension = path.extname(absolutePath).toLowerCase();
  return SOURCE_EXTENSIONS.has(extension) || TEXT_CONTENT_EXTENSIONS.has(extension);
}

function shouldReadAsText(absolutePath: string): boolean {
  return TEXT_CONTENT_EXTENSIONS.has(path.extname(absolutePath).toLowerCase());
}

function isSourceFormat(format: RobotFile['format'] | null): format is Exclude<RobotFile['format'], 'usd' | 'asset'> {
  return format === 'mjcf' || format === 'sdf' || format === 'urdf' || format === 'xacro';
}

function shouldValidateImportFile(
  format: RobotFile['format'] | null,
  content: string,
): format is Exclude<RobotFile['format'], 'usd' | 'asset' | 'xacro'> {
  return isSourceFormat(format) && format !== 'xacro' && !hasTemplatePlaceholder(content);
}

function isUsdPath(filePath: string): boolean {
  return USD_EXTENSIONS.has(path.extname(filePath).toLowerCase());
}

function isUsdDependencyLayer(fileName: string): boolean {
  const normalized = normalizePath(fileName);
  return normalized.includes('/configuration/') || isLikelyNonRenderableUsdConfigPath(normalized);
}

async function listImmediateChildDirs(
  rootDir: string,
  options: { excludeDirNames?: string[] } = {},
): Promise<string[]> {
  const excluded = new Set(options.excludeDirNames ?? []);
  const entries = await readdir(rootDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith('.') && !excluded.has(entry.name))
    .map((entry) => path.join(rootDir, entry.name))
    .sort((left, right) => left.localeCompare(right));
}

async function discoverSourceSupportRoots(rootDir: string): Promise<string[]> {
  const absolutePaths = await collectFiles(rootDir);
  const supportRoots = new Set<string>();

  for (const absolutePath of absolutePaths) {
    if (!SOURCE_EXTENSIONS.has(path.extname(absolutePath).toLowerCase())) {
      continue;
    }
    if (!shouldReadAsText(absolutePath)) {
      continue;
    }

    const relativePath = toDatasetRelative(rootDir, absolutePath);
    const content = await readFile(absolutePath, 'utf8');
    const format = detectFixtureFormat(relativePath, content);
    if (!shouldValidateImportFile(format, content)) {
      continue;
    }

    supportRoots.add(path.dirname(absolutePath));
  }

  return [...supportRoots].sort((left, right) => left.localeCompare(right));
}

async function discoverUsdSupportRoots(rootDir: string): Promise<string[]> {
  const absolutePaths = await collectFiles(rootDir);
  const supportRoots = new Set<string>();

  for (const absolutePath of absolutePaths) {
    if (!isUsdPath(absolutePath)) {
      continue;
    }
    const relativePath = toDatasetRelative(rootDir, absolutePath);
    const parentDir = path.posix.dirname(relativePath);
    if (relativePath.includes('/configuration/')) {
      supportRoots.add(path.resolve(rootDir, path.posix.dirname(parentDir)));
      continue;
    }
    supportRoots.add(path.resolve(rootDir, parentDir));
  }

  return [...supportRoots].sort((left, right) => left.localeCompare(right));
}

async function collectFiles(rootDir: string): Promise<string[]> {
  const files: string[] = [];

  async function visit(currentDir: string) {
    const entries = await readdir(currentDir, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (entry.name.startsWith('.')) {
        continue;
      }
      const absolutePath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await visit(absolutePath);
        continue;
      }
      if (entry.isFile()) {
        files.push(absolutePath);
      }
    }
  }

  await visit(rootDir);
  return files;
}

async function pathExists(targetPath: string): Promise<boolean> {
  try {
    await access(targetPath);
    return true;
  } catch {
    return false;
  }
}

function toDatasetRelative(rootDir: string, absolutePath: string): string {
  return normalizePath(path.relative(rootDir, absolutePath));
}

function toRepoRelative(absolutePath: string): string {
  return normalizePath(path.relative(process.cwd(), absolutePath));
}

function normalizePath(filePath: string): string {
  return filePath.replace(/\\/g, '/').replace(/^\/+/, '');
}
