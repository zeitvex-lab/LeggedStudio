#!/usr/bin/env node

import { access, mkdir, readFile, readdir, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const OUTPUT_PATH = path.resolve('tmp/regression/unitree-browser-selected.json');
const SITE_URL = 'http://127.0.0.1:4173/?regressionDebug=1';
const SITE_BASE_URL = 'http://127.0.0.1:4173';
export const BUILTIN_UNITREE_MODEL_ENTRIES = [
  {
    modelKey: 'Go2',
    loadFileName: 'unitree_model/Go2/usd/go2.usd',
  },
  {
    modelKey: 'Go2W',
    loadFileName: 'unitree_model/Go2W/usd/go2w.usd',
  },
  {
    modelKey: 'B2',
    loadFileName: 'unitree_model/B2/usd/b2.usd',
  },
  {
    modelKey: 'H1',
    loadFileName: 'unitree_model/H1/h1/usd/h1.usd',
  },
  {
    modelKey: 'H1-2',
    loadFileName: 'unitree_model/H1-2/h1_2/h1_2.usd',
  },
  {
    modelKey: 'H1-2-Handless',
    loadFileName: 'unitree_model/H1-2/h1_2_handless/h1_2_handless.usd',
  },
  {
    modelKey: 'G1-23DoF',
    loadFileName: 'unitree_model/G1/23dof/usd/g1_23dof_rev_1_0/g1_23dof_rev_1_0.usd',
  },
  {
    modelKey: 'G1-29DoF',
    loadFileName: 'unitree_model/G1/29dof/usd/g1_29dof_rev_1_0/g1_29dof_rev_1_0.usd',
  },
];
const MODELS = BUILTIN_UNITREE_MODEL_ENTRIES.map((entry) => entry.modelKey);
const MAX_ATTEMPTS = 2;
const SITE_TIMEOUT_MS = 120_000;
const MODEL_TIMEOUT_MS = 600_000;
const UNITREE_MODEL_ROOT = path.resolve('test/unitree_model');

function runCommand(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      stdio: 'inherit',
      env: process.env,
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

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, 'utf8'));
}

async function pathExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function normalizeRelativePath(value) {
  return String(value || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '');
}

async function collectUsdFiles(rootDir) {
  const files = [];

  async function visit(currentDir) {
    const entries = await readdir(currentDir, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await visit(fullPath);
        continue;
      }
      if (entry.isFile() && /\.usda?$/i.test(entry.name)) {
        files.push(fullPath);
      }
    }
  }

  await visit(rootDir);
  return files;
}

function isTopLevelUnitreeUsdEntrypoint(relativePath) {
  const normalized = normalizeRelativePath(relativePath);
  const lower = normalized.toLowerCase();
  if (!lower.endsWith('.usd') && !lower.endsWith('.usda')) {
    return false;
  }
  if (lower.includes('/configuration/')) {
    return false;
  }
  if (lower.endsWith('.viewer_roundtrip.usd')) {
    return false;
  }
  return true;
}

export async function findUnregisteredTopLevelUnitreeUsdEntrypoints() {
  if (!(await pathExists(UNITREE_MODEL_ROOT))) {
    return [];
  }

  const registeredEntrypoints = new Set(
    BUILTIN_UNITREE_MODEL_ENTRIES.map((entry) => normalizeRelativePath(entry.loadFileName)),
  );
  const files = await collectUsdFiles(UNITREE_MODEL_ROOT);
  return files
    .map((filePath) => normalizeRelativePath(path.relative(path.resolve('test'), filePath)))
    .filter(isTopLevelUnitreeUsdEntrypoint)
    .filter((relativePath) => !registeredEntrypoints.has(relativePath));
}

async function assertRegisteredUnitreeCoverage() {
  const missing = await findUnregisteredTopLevelUnitreeUsdEntrypoints();
  if (missing.length > 0) {
    throw new Error(
      [
        'Unregistered top-level Unitree USD model entrypoint(s) found in test/unitree_model.',
        'Register each entry in scripts/test/browser/run_unitree_browser_regression.mjs and scripts/test/browser/validate_unitree_selected_browser.mjs before running full validation:',
        ...missing.map((entrypoint) => `  - ${entrypoint}`),
      ].join('\n'),
    );
  }
}

async function isSiteReachable(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      redirect: 'follow',
      cache: 'no-store',
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function ensureSite() {
  if (await isSiteReachable(SITE_BASE_URL)) {
    return { stop: async () => {} };
  }

  const child = spawn(
    'npm',
    ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '4173', '--strictPort'],
    {
      cwd: process.cwd(),
      stdio: 'inherit',
      env: process.env,
      detached: true,
    },
  );

  const deadline = Date.now() + SITE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await isSiteReachable(SITE_BASE_URL)) {
      return {
        stop: async () => {
          if (child.exitCode != null || child.signalCode != null) return;
          try {
            process.kill(-child.pid, 'SIGTERM');
          } catch {}
          await delay(500);
        },
      };
    }
    if (child.exitCode != null) {
      throw new Error(`preview process exited early with code ${child.exitCode}`);
    }
    await delay(500);
  }

  throw new Error(`Timed out waiting for preview at ${SITE_BASE_URL}`);
}

function hasResolvedRobotData(result) {
  return (
    result?.workerResolveEntry?.status === 'resolved' ||
    result?.runtimeResolveEntry?.status === 'resolved'
  );
}

function hasPreparedRobotStateCache(result) {
  const preparedCacheKeys =
    result?.assetDebugState?.preparedUsdCacheKeysByFile?.[result?.selectedFileName] ??
    result?.assetDebugState?.preparedUsdCacheKeysByFile?.[result?.targetFileName] ??
    null;
  return Array.isArray(preparedCacheKeys) && preparedCacheKeys.length > 0;
}

function hasRobotStateRenderEvidence(result) {
  return Boolean(
    hasPreparedRobotStateCache(result) ||
      result?.stageReady === true ||
      result?.selectedUsdSceneSummary?.available === true,
  );
}

function hasFiniteVector(value, expectedLength) {
  return (
    Array.isArray(value) &&
    value.length === expectedLength &&
    value.every((entry) => Number.isFinite(Number(entry)))
  );
}

export function hasSceneBindingCoverage(result) {
  const sceneSummary = result?.selectedUsdSceneSummary;
  const baseLink = sceneSummary?.baseLink;
  if (!sceneSummary || !baseLink) {
    return false;
  }

  const hasAnyBaseLinkBinding =
    baseLink.bindingSummary?.withDescriptorMaterialId > 0 ||
    baseLink.bindingSummary?.withGeometryMaterialId > 0 ||
    baseLink.bindingSummary?.withGeomSubsetSections > 0;
  const linkTransform = baseLink.transform ?? baseLink.runtimeLinkTransform ?? null;
  const maxDimension = hasFiniteVector(baseLink.bounds?.size, 3)
    ? Math.max(...baseLink.bounds.size.map((entry) => Number(entry)))
    : Number.NaN;
  const hasRuntimeBaseLinkTransform =
    (hasFiniteVector(linkTransform?.position, 3) &&
      hasFiniteVector(linkTransform?.quaternion, 4)) ||
    (Array.isArray(baseLink.runtimeVisualMeshTransforms) &&
      baseLink.runtimeVisualMeshTransforms.some(
        (entry) => hasFiniteVector(entry?.position, 3) && hasFiniteVector(entry?.quaternion, 4),
      ));
  const hasPreparedMeshCache = hasPreparedRobotStateCache(result);

  return Boolean(
    sceneSummary.available === true &&
    sceneSummary.fileName === result?.selectedFileName &&
    baseLink.found === true &&
    baseLink.visualDescriptorCount > 0 &&
    hasAnyBaseLinkBinding &&
    baseLink.bindingSummary?.withoutAnyMaterialBinding < baseLink.bindingSummary?.descriptorCount &&
    hasFiniteVector(baseLink.bounds?.size, 3) &&
    baseLink.bounds.size.every((entry) => Number(entry) > 0) &&
    Number.isFinite(maxDimension) &&
    maxDimension < 10 &&
    (hasRuntimeBaseLinkTransform || hasPreparedMeshCache),
  );
}

function hasExpectedB2VisualMaterialRendering(result) {
  const targetPath = String(result?.selectedFileName || result?.targetFileName || '').toLowerCase();
  if (!targetPath.includes('unitree_model/b2/')) {
    return true;
  }

  const summary = result?.selectedUsdVisualMaterialSummary;
  if (!summary || !Array.isArray(summary.meshes) || summary.meshes.length === 0) {
    return false;
  }

  const materialColorsByName = new Map();
  for (const mesh of summary.meshes) {
    if (mesh?.overrideColor || mesh?.hasOverrideMaterial) {
      return false;
    }
    const materials = Array.isArray(mesh?.materials) ? mesh.materials : [];
    for (const material of materials) {
      const name = String(material?.name || '').trim();
      const color = String(material?.color || '')
        .trim()
        .toLowerCase();
      const emissive = String(material?.emissive || '')
        .trim()
        .toLowerCase();
      if (emissive && emissive !== '#000000') {
        return false;
      }
      if (name && color && !materialColorsByName.has(name)) {
        materialColorsByName.set(name, color);
      }
    }
  }

  const parseHexColor = (value) => {
    const normalized = String(value || '')
      .trim()
      .toLowerCase();
    const match = /^#([0-9a-f]{6})$/.exec(normalized);
    return match ? Number.parseInt(match[1], 16) : Number.NaN;
  };

  const accentColor = parseHexColor(materialColorsByName.get('material_______024'));
  return (
    materialColorsByName.get('material_______023') === '#000000' &&
    Number.isFinite(accentColor) &&
    accentColor >= 0x000000 &&
    accentColor <= 0x101010
  );
}

function isB2Result(result) {
  const targetPath = normalizeRelativePath(result?.selectedFileName || result?.targetFileName);
  return targetPath.toLowerCase().includes('unitree_model/b2/');
}

export function hasPreservedAuthoredUsdVisualMaterialColors(result) {
  const summary = result?.selectedUsdVisualMaterialSummary;
  if (!summary || !Array.isArray(summary.meshes) || summary.meshes.length === 0) {
    return false;
  }

  let authoredMaterialCount = 0;
  for (const mesh of summary.meshes) {
    const materials = Array.isArray(mesh?.materials) ? mesh.materials : [];
    for (const material of materials) {
      const color = String(material?.color || '')
        .trim()
        .toLowerCase();
      const authoredColor = String(material?.authoredColor || '')
        .trim()
        .toLowerCase();
      const colorSource = String(material?.colorSource || '')
        .trim()
        .toLowerCase()
        .replace(/[_\s]+/g, '-');

      if (colorSource === 'authored' && !authoredColor) {
        return false;
      }
      if (!authoredColor) {
        continue;
      }
      authoredMaterialCount += 1;
      if (color !== authoredColor) {
        return false;
      }
    }
  }

  return authoredMaterialCount > 0;
}

function extractNormalDiagnosticEntries(value, seen = new WeakSet()) {
  if (!value || typeof value !== 'object') {
    return [];
  }
  if (seen.has(value)) {
    return [];
  }
  seen.add(value);

  const entries = [];
  const hasDirectDiagnostic =
    Object.hasOwn(value, 'normalRepairCount') || Object.hasOwn(value, 'postRepairLowDotCount');
  if (hasDirectDiagnostic) {
    entries.push(value);
  }

  if (value.normalDiagnostics && typeof value.normalDiagnostics === 'object') {
    entries.push(...extractNormalDiagnosticEntries(value.normalDiagnostics, seen));
  }
  if (value.normalDiagnostic && typeof value.normalDiagnostic === 'object') {
    entries.push(...extractNormalDiagnosticEntries(value.normalDiagnostic, seen));
  }

  for (const child of Object.values(value)) {
    if (!child || typeof child !== 'object') {
      continue;
    }
    if (child === value.normalDiagnostics || child === value.normalDiagnostic) {
      continue;
    }
    if (Array.isArray(child)) {
      for (const item of child) {
        entries.push(...extractNormalDiagnosticEntries(item, seen));
      }
      continue;
    }
    entries.push(...extractNormalDiagnosticEntries(child, seen));
  }

  return entries;
}

export function hasExpectedB2NormalDiagnostics(result) {
  if (!isB2Result(result)) {
    return true;
  }

  const diagnostics = extractNormalDiagnosticEntries({
    selectedUsdSceneSummary: result?.selectedUsdSceneSummary ?? null,
    selectedUsdNormalDiagnostics: result?.selectedUsdNormalDiagnostics ?? null,
    normalDiagnostics: result?.normalDiagnostics ?? null,
  });
  if (diagnostics.length === 0) {
    return false;
  }

  const repairedDiagnostics = diagnostics.filter(
    (entry) => Number(entry?.normalRepairCount ?? 0) > 0,
  );
  const isFiniteZeroPostRepair = (entry) => {
    if (!Object.hasOwn(entry, 'postRepairLowDotCount')) {
      return false;
    }
    const postRepairLowDotCount = entry?.postRepairLowDotCount;
    return (
      postRepairLowDotCount != null &&
      Number.isFinite(Number(postRepairLowDotCount)) &&
      Number(postRepairLowDotCount) === 0
    );
  };
  const hasPostRepairLowDotFailure = diagnostics.some((entry) => {
    if (!Object.hasOwn(entry, 'postRepairLowDotCount')) {
      return false;
    }
    return !isFiniteZeroPostRepair(entry);
  });

  return (
    repairedDiagnostics.length > 0 &&
    repairedDiagnostics.every(isFiniteZeroPostRepair) &&
    !hasPostRepairLowDotFailure
  );
}

function validateResult(result) {
  return Boolean(
    result?.loaded === true &&
    hasResolvedRobotData(result) &&
    result?.workerResolveEntry?.status === 'resolved' &&
    result?.documentLoadState?.status === 'ready' &&
    hasRobotStateRenderEvidence(result) &&
    result?.metadataSourcePass === true &&
    hasSceneBindingCoverage(result) &&
    hasExpectedB2VisualMaterialRendering(result) &&
    hasPreservedAuthoredUsdVisualMaterialColors(result) &&
    hasExpectedB2NormalDiagnostics(result) &&
    (result?.consoleErrors?.length ?? 0) === 0 &&
    (result?.consoleWarnings?.length ?? 0) === 0 &&
    (result?.pageErrors?.length ?? 0) === 0,
  );
}

function summarizeFailures(report) {
  return (report?.results || [])
    .filter((result) => !validateResult(result))
    .map((result) => ({
      sampleId: result.sampleId,
      loaded: result.loaded,
      runtimePresent: result.runtimePresent,
      workerResolveStatus: result.workerResolveEntry?.status ?? null,
      runtimeResolveStatus: result.runtimeResolveEntry?.status ?? null,
      stageReady: result.stageReady,
      stagePreparationMode: result.stagePreparationMode,
      metadataSource: result.metadataSource,
      metadataSourcePass: result.metadataSourcePass,
      hasPreparedRobotStateCache: hasPreparedRobotStateCache(result),
      hasRobotStateRenderEvidence: hasRobotStateRenderEvidence(result),
      selectedUsdSceneSummary: result.selectedUsdSceneSummary ?? null,
      selectedUsdVisualMaterialSummary: result.selectedUsdVisualMaterialSummary ?? null,
      selectedUsdNormalDiagnostics: result.selectedUsdNormalDiagnostics ?? null,
      normalDiagnostics: result.normalDiagnostics ?? null,
      orbitInteraction: result.orbitInteraction ?? null,
      consoleErrors: result.consoleErrors,
      consoleWarnings: result.consoleWarnings,
      pageErrors: result.pageErrors,
    }));
}

function buildPerModelOutputPath(modelKey) {
  const fileName = modelKey.replace(/[\\/]/g, '__').replace(/[^a-zA-Z0-9._-]+/g, '_');
  return path.resolve('tmp/regression/unitree-browser-selected', `${fileName}.json`);
}

async function writeAggregateReport(results) {
  const report = {
    generatedAtUtc: new Date().toISOString(),
    workspace: process.cwd(),
    siteUrl: SITE_URL,
    summary: {
      modelCount: MODELS.length,
      passedCount: results.filter((result) => validateResult(result)).length,
      failedCount: results.filter((result) => !validateResult(result)).length,
      models: MODELS,
    },
    results,
  };

  await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await writeFile(OUTPUT_PATH, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  return report;
}

async function runModelRegression(modelKey) {
  let lastError = null;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const modelOutputPath = buildPerModelOutputPath(modelKey);
    try {
      await unlink(modelOutputPath).catch(() => {});
      await runCommand('node', [
        'scripts/test/browser/run_unitree_browser_regression.mjs',
        '--site-url',
        SITE_URL,
        '--no-start',
        '--timeout-ms',
        String(MODEL_TIMEOUT_MS),
        '--output',
        modelOutputPath,
        '--model',
        modelKey,
      ]);
      if (!(await pathExists(modelOutputPath))) {
        throw new Error(`Missing regression output for ${modelKey}`);
      }
      const report = await readJson(modelOutputPath);
      const result = report?.results?.[0] ?? null;
      if (result) {
        return result;
      }
      throw new Error(`Missing regression result for ${modelKey}`);
    } catch (error) {
      lastError = error;
      if (attempt < MAX_ATTEMPTS) {
        console.warn(
          `[validate-unitree-selected-browser] retrying model ${modelKey} after attempt ${attempt}: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }
  }

  return {
    modelKey,
    sampleId: modelKey,
    error: lastError instanceof Error ? lastError.message : String(lastError),
    loaded: false,
    runtimePresent: false,
    workerResolveEntry: null,
    runtimeResolveEntry: null,
    stageReady: false,
    stagePreparationMode: null,
    metadataSource: null,
    metadataSourcePass: false,
    selectedUsdSceneSummary: null,
    selectedUsdVisualMaterialSummary: null,
    orbitInteraction: null,
    consoleErrors: [],
    consoleWarnings: [],
    pageErrors: [],
  };
}

async function main() {
  await assertRegisteredUnitreeCoverage();
  const site = await ensureSite();
  try {
    const results = [];
    for (const modelKey of MODELS) {
      results.push(await runModelRegression(modelKey));
    }
    const report = await writeAggregateReport(results);
    const failures = summarizeFailures(report);
    if (failures.length === 0) {
      console.log(
        JSON.stringify(
          {
            output: OUTPUT_PATH,
            modelCount: report.summary.modelCount,
            passedCount: report.summary.passedCount,
            failedCount: 0,
          },
          null,
          2,
        ),
      );
      return;
    }

    throw new Error(`Unitree USD browser validation failed: ${JSON.stringify(failures, null, 2)}`);
  } finally {
    await site.stop();
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : error);
    process.exitCode = 1;
  });
}
