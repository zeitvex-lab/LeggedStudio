import { buildAssetIndex } from '@/core/loaders/meshLoader';
import type { RobotFile } from '@/types';
import { MJCF_SOURCE_FILE_SCOPE_ATTR } from './mjcfSourceResolver';
import { parseCompilerSettings, parseMJCFXmlDocument } from './mjcfUtils';

export type MJCFImportExternalAssetKind = 'mesh' | 'texture' | 'hfield' | 'model' | 'include';

export interface MJCFImportExternalAssetIssue {
  kind: 'missing_external_asset';
  referenceKind: MJCFImportExternalAssetKind;
  attributeName: string;
  rawPath: string;
  resolvedPath: string;
  sourceFilePath: string;
  elementName: string | null;
  detail: string;
}

export interface MJCFImportExternalAssetValidationSummary {
  issues: MJCFImportExternalAssetIssue[];
  referencedAssetCount: number;
  resolvedAssetCount: number;
}

const TEXTURE_FILE_ATTRIBUTES = [
  'file',
  'fileback',
  'filedown',
  'filefront',
  'fileleft',
  'fileright',
  'fileup',
] as const;

interface MJCFCompilerDirectorySettings {
  assetdir: string;
  meshdir: string;
  texturedir: string;
}

function stripFileScheme(filePath: string): string {
  const trimmed = String(filePath || '').trim();
  if (!/^file:\/\//i.test(trimmed)) {
    return trimmed;
  }

  try {
    const parsed = new URL(trimmed);
    return decodeURIComponent(parsed.pathname).replace(/^\/([A-Za-z]:\/)/, '$1');
  } catch {
    return trimmed.replace(/^file:\/\/*/i, '');
  }
}

function normalizeLookupPath(filePath: string): string {
  const normalized = stripFileScheme(filePath).replace(/\\/g, '/').replace(/\/+/g, '/').trim();
  if (!normalized) {
    return '';
  }

  const isAbsolute = normalized.startsWith('/');
  const segments = normalized.split('/').filter(Boolean);
  const resolved: string[] = [];

  for (const segment of segments) {
    if (segment === '.') {
      continue;
    }

    if (segment === '..') {
      if (resolved.length > 0 && resolved[resolved.length - 1] !== '..') {
        resolved.pop();
        continue;
      }

      if (!isAbsolute) {
        resolved.push(segment);
      }
      continue;
    }

    resolved.push(segment);
  }

  if (resolved.length === 0) {
    return isAbsolute ? '/' : '';
  }

  return `${isAbsolute ? '/' : ''}${resolved.join('/')}`;
}

function getDirectoryPath(filePath: string): string {
  const normalized = normalizeLookupPath(filePath);
  if (!normalized) {
    return '';
  }

  const lastSlash = normalized.lastIndexOf('/');
  if (lastSlash <= 0) {
    return normalized.startsWith('/') ? '/' : '';
  }

  return normalized.slice(0, lastSlash);
}

function joinLookupPath(basePath: string, relativePath: string): string {
  if (!basePath) {
    return normalizeLookupPath(relativePath);
  }

  if (!relativePath) {
    return normalizeLookupPath(basePath);
  }

  return normalizeLookupPath(`${basePath}/${relativePath}`);
}

function applyAssetDirectory(filePath: string, directory: string): string {
  const trimmed = filePath.trim();
  if (!trimmed || trimmed.startsWith('/') || trimmed.includes(':')) {
    return normalizeLookupPath(trimmed);
  }

  const normalizedDirectory = normalizeLookupPath(directory);
  if (!normalizedDirectory) {
    return normalizeLookupPath(trimmed);
  }

  const normalizedTrimmed = normalizeLookupPath(trimmed);
  const shouldTreatReferenceAsAlreadyScoped =
    !normalizedDirectory
      .split('/')
      .filter(Boolean)
      .every((segment) => segment === '..') &&
    (normalizedTrimmed === normalizedDirectory ||
      normalizedTrimmed.startsWith(`${normalizedDirectory}/`));

  if (shouldTreatReferenceAsAlreadyScoped) {
    return normalizedTrimmed;
  }

  return normalizeLookupPath(`${normalizedDirectory}/${trimmed}`);
}

function resolveAssetReferencePath(
  sourceFilePath: string,
  rawPath: string,
  compilerDirectory: string,
): string {
  const compilerScopedPath = applyAssetDirectory(rawPath, compilerDirectory);
  if (
    !compilerScopedPath ||
    compilerScopedPath.startsWith('/') ||
    compilerScopedPath.includes(':')
  ) {
    return compilerScopedPath;
  }

  return joinLookupPath(getDirectoryPath(sourceFilePath), compilerScopedPath);
}

function buildKnownAssetLookup(
  availableFiles: RobotFile[],
  assets: Record<string, string>,
): Record<string, string> {
  const knownAssets: Record<string, string> = {};

  availableFiles.forEach((file) => {
    const normalized = normalizeLookupPath(file.name);
    if (normalized) {
      knownAssets[normalized] = normalized;
    }
  });

  Object.keys(assets).forEach((assetPath) => {
    const normalized = normalizeLookupPath(assetPath);
    if (normalized) {
      knownAssets[normalized] = normalized;
    }
  });

  return knownAssets;
}

function buildAdjacentDuplicateCollapsedVariants(assetPath: string): string[] {
  const normalizedPath = normalizeLookupPath(assetPath);
  if (!normalizedPath) {
    return [];
  }

  const hasLeadingSlash = normalizedPath.startsWith('/');
  const segments = normalizedPath.split('/').filter(Boolean);
  const variants: string[] = [];

  for (let index = 1; index < segments.length; index += 1) {
    if (segments[index] !== segments[index - 1]) {
      continue;
    }

    const nextSegments = [...segments];
    nextSegments.splice(index, 1);
    const variant = `${hasLeadingSlash ? '/' : ''}${nextSegments.join('/')}`;
    if (variant && variant !== normalizedPath && !variants.includes(variant)) {
      variants.push(variant);
    }
  }

  return variants;
}

function buildDirectoryCollapsedVariants(assetPath: string): string[] {
  const normalizedPath = normalizeLookupPath(assetPath);
  if (!normalizedPath) {
    return [];
  }

  const hasLeadingSlash = normalizedPath.startsWith('/');
  const segments = normalizedPath.split('/').filter(Boolean);
  const variants: string[] = [];

  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index]?.toLowerCase();
    if (segment !== 'mesh' && segment !== 'meshes' && segment !== 'asset' && segment !== 'assets') {
      continue;
    }

    const suffix = segments.slice(index + 1);
    if (suffix.length === 0) {
      continue;
    }

    const variant = `${hasLeadingSlash ? '/' : ''}${suffix.join('/')}`;
    if (variant && variant !== normalizedPath && !variants.includes(variant)) {
      variants.push(variant);
    }
  }

  return variants;
}

function buildMeshExtensionVariants(assetPath: string): string[] {
  const normalizedPath = normalizeLookupPath(assetPath);
  const extensionMatch = normalizedPath.match(/\.[^.\/]+$/);
  if (!extensionMatch) {
    return [];
  }

  const extension = extensionMatch[0].toLowerCase();
  return ['.dae', '.obj', '.stl', '.msh', '.gltf', '.glb', '.ply', '.vtk']
    .filter((candidateExtension) => candidateExtension !== extension)
    .map((candidateExtension) => normalizedPath.replace(/\.[^.\/]+$/, candidateExtension));
}

function hasExactAssetPathMatch(
  assetIndex: ReturnType<typeof buildAssetIndex>,
  assetPath: string,
): boolean {
  return assetIndex.direct.has(assetPath) || assetIndex.lowercase.has(assetPath.toLowerCase());
}

function hasValidatedAssetMatch(
  assetIndex: ReturnType<typeof buildAssetIndex>,
  assetPath: string,
  referenceKind: MJCFImportExternalAssetKind,
): boolean {
  const normalizedPath = normalizeLookupPath(assetPath);
  if (!normalizedPath) {
    return false;
  }

  const allowFuzzyAssetMatch =
    referenceKind === 'mesh' || referenceKind === 'hfield' || referenceKind === 'model';
  const candidatePaths = [
    normalizedPath,
    normalizedPath.replace(/^\/+/, ''),
    ...buildAdjacentDuplicateCollapsedVariants(normalizedPath),
    ...(allowFuzzyAssetMatch ? buildDirectoryCollapsedVariants(normalizedPath) : []),
    ...(allowFuzzyAssetMatch ? buildMeshExtensionVariants(normalizedPath) : []),
  ].filter((candidate, index, all) => candidate && all.indexOf(candidate) === index);

  return candidatePaths.some(
    (candidatePath) => {
      const filename = candidatePath.split('/').pop() || '';
      const filenameLower = filename.toLowerCase();
      return (
        hasExactAssetPathMatch(assetIndex, candidatePath) ||
        (candidatePath.startsWith('/') &&
          hasExactAssetPathMatch(assetIndex, candidatePath.replace(/^\/+/, ''))) ||
        (allowFuzzyAssetMatch &&
          (Boolean(filenameLower && assetIndex.filenameLower.has(filenameLower)) ||
            assetIndex.cleanedPaths.some((knownPath) => {
              const knownLower = knownPath.toLowerCase();
              const candidateLower = candidatePath.toLowerCase().replace(/^\/+/, '');
              return (
                knownLower.endsWith(`/${candidateLower}`) ||
                candidateLower.endsWith(`/${knownLower}`)
              );
            })))
      );
    },
  );
}

function collectDirectChildElements(parent: Element, tagName: string): Element[] {
  const normalizedTagName = tagName.toLowerCase();
  return Array.from(parent.children).filter(
    (child) => child.tagName.toLowerCase() === normalizedTagName,
  );
}

function buildCompilerSettingsBySource(
  availableFiles: RobotFile[],
): Map<string, MJCFCompilerDirectorySettings> {
  const settingsBySource = new Map<string, MJCFCompilerDirectorySettings>();

  availableFiles.forEach((file) => {
    if (file.format !== 'mjcf' || typeof file.content !== 'string' || !file.content.trim()) {
      return;
    }

    const { doc } = parseMJCFXmlDocument(file.content);
    if (!doc) {
      return;
    }

    const hasAssetDirectoryCompiler = Array.from(doc.querySelectorAll('compiler')).some(
      (compilerEl) =>
        compilerEl.hasAttribute('assetdir') ||
        compilerEl.hasAttribute('meshdir') ||
        compilerEl.hasAttribute('texturedir'),
    );
    if (!hasAssetDirectoryCompiler) {
      return;
    }

    const settings = parseCompilerSettings(doc);
    const sourcePath = file.name.trim();
    const normalizedSourcePath = normalizeLookupPath(sourcePath);
    if (sourcePath) {
      settingsBySource.set(sourcePath, settings);
    }
    if (normalizedSourcePath) {
      settingsBySource.set(normalizedSourcePath, settings);
    }
  });

  return settingsBySource;
}

function resolveScopedSourceFilePath(element: Element, fallbackSourceFilePath: string): string {
  let current: Element | null = element;
  while (current) {
    const scopedSourcePath = current.getAttribute(MJCF_SOURCE_FILE_SCOPE_ATTR)?.trim();
    if (scopedSourcePath) {
      return scopedSourcePath;
    }

    current = current.parentElement;
  }

  return fallbackSourceFilePath;
}

function getCompilerSettingsForSource(
  sourceFilePath: string,
  settingsBySource: Map<string, MJCFCompilerDirectorySettings>,
  fallbackSettings: MJCFCompilerDirectorySettings,
): MJCFCompilerDirectorySettings {
  const normalizedSourceFilePath = normalizeLookupPath(sourceFilePath);
  return (
    settingsBySource.get(sourceFilePath) ??
    (normalizedSourceFilePath ? settingsBySource.get(normalizedSourceFilePath) : undefined) ??
    fallbackSettings
  );
}

function getCompilerDirectoryForReferenceKind(
  settings: MJCFCompilerDirectorySettings,
  referenceKind: MJCFImportExternalAssetKind,
): string {
  if (referenceKind === 'mesh') {
    return settings.meshdir;
  }

  if (referenceKind === 'texture') {
    return settings.texturedir;
  }

  if (referenceKind === 'hfield' || referenceKind === 'model') {
    return settings.assetdir;
  }

  return '';
}

function resolveElementReferenceContext(
  element: Element,
  referenceKind: MJCFImportExternalAssetKind,
  options: {
    fallbackSourceFilePath: string;
    fallbackSettings: MJCFCompilerDirectorySettings;
    settingsBySource: Map<string, MJCFCompilerDirectorySettings>;
  },
): {
  sourceFilePath: string;
  compilerDirectory: string;
} {
  const sourceFilePath = resolveScopedSourceFilePath(element, options.fallbackSourceFilePath);
  const settings = getCompilerSettingsForSource(
    sourceFilePath,
    options.settingsBySource,
    options.fallbackSettings,
  );

  return {
    sourceFilePath,
    compilerDirectory: getCompilerDirectoryForReferenceKind(settings, referenceKind),
  };
}

function collectMissingAssetIssue(
  assetIndex: ReturnType<typeof buildAssetIndex>,
  options: {
    sourceFilePath: string;
    referenceKind: MJCFImportExternalAssetKind;
    attributeName: string;
    rawPath: string | null;
    compilerDirectory: string;
    elementName: string | null;
  },
): MJCFImportExternalAssetIssue | 'matched' | null {
  const rawPath = options.rawPath?.trim();
  if (!rawPath) {
    return null;
  }

  const resolvedPath = resolveAssetReferencePath(
    options.sourceFilePath,
    rawPath,
    options.compilerDirectory,
  );
  if (!resolvedPath) {
    return null;
  }

  if (hasValidatedAssetMatch(assetIndex, resolvedPath, options.referenceKind)) {
    return 'matched';
  }

  const label = options.elementName
    ? `${options.referenceKind} "${options.elementName}"`
    : `${options.referenceKind} asset`;
  return {
    kind: 'missing_external_asset',
    referenceKind: options.referenceKind,
    attributeName: options.attributeName,
    rawPath,
    resolvedPath,
    sourceFilePath: options.sourceFilePath,
    elementName: options.elementName,
    detail: `Referenced MJCF ${label} file "${resolvedPath}" could not be resolved from "${options.sourceFilePath}".`,
  };
}

function appendAssetValidationOutcome(
  summary: MJCFImportExternalAssetValidationSummary,
  assetIndex: ReturnType<typeof buildAssetIndex>,
  options: {
    sourceFilePath: string;
    referenceKind: MJCFImportExternalAssetKind;
    attributeName: string;
    rawPath: string | null;
    compilerDirectory: string;
    elementName: string | null;
  },
): void {
  const outcome = collectMissingAssetIssue(assetIndex, options);
  if (!outcome) {
    return;
  }

  summary.referencedAssetCount += 1;
  if (outcome === 'matched') {
    summary.resolvedAssetCount += 1;
    return;
  }

  summary.issues.push(outcome);
}

export function inspectMJCFImportExternalAssets(
  sourceFilePath: string,
  content: string,
  availableFiles: RobotFile[],
  assets: Record<string, string>,
): MJCFImportExternalAssetValidationSummary {
  const { doc } = parseMJCFXmlDocument(content);
  if (!doc) {
    return {
      issues: [],
      referencedAssetCount: 0,
      resolvedAssetCount: 0,
    };
  }

  const mujocoEl = doc.querySelector('mujoco');
  if (!mujocoEl) {
    return {
      issues: [],
      referencedAssetCount: 0,
      resolvedAssetCount: 0,
    };
  }

  const settings = parseCompilerSettings(doc);
  const settingsBySource = buildCompilerSettingsBySource(availableFiles);
  const knownAssetLookup = buildKnownAssetLookup(availableFiles, assets);
  const assetIndex = buildAssetIndex(knownAssetLookup);
  const summary: MJCFImportExternalAssetValidationSummary = {
    issues: [],
    referencedAssetCount: 0,
    resolvedAssetCount: 0,
  };
  const assetSections = collectDirectChildElements(mujocoEl, 'asset');

  collectDirectChildElements(mujocoEl, 'include').forEach((includeEl) => {
    const context = resolveElementReferenceContext(includeEl, 'include', {
      fallbackSourceFilePath: sourceFilePath,
      fallbackSettings: settings,
      settingsBySource,
    });
    appendAssetValidationOutcome(summary, assetIndex, {
      sourceFilePath: context.sourceFilePath,
      referenceKind: 'include',
      attributeName: 'file',
      rawPath: includeEl.getAttribute('file'),
      compilerDirectory: context.compilerDirectory,
      elementName: null,
    });
  });

  assetSections.forEach((assetEl) => {
    collectDirectChildElements(assetEl, 'mesh').forEach((meshEl) => {
      const context = resolveElementReferenceContext(meshEl, 'mesh', {
        fallbackSourceFilePath: sourceFilePath,
        fallbackSettings: settings,
        settingsBySource,
      });
      appendAssetValidationOutcome(summary, assetIndex, {
        sourceFilePath: context.sourceFilePath,
        referenceKind: 'mesh',
        attributeName: 'file',
        rawPath: meshEl.getAttribute('file'),
        compilerDirectory: context.compilerDirectory,
        elementName: meshEl.getAttribute('name'),
      });
    });

    collectDirectChildElements(assetEl, 'texture').forEach((textureEl) => {
      const context = resolveElementReferenceContext(textureEl, 'texture', {
        fallbackSourceFilePath: sourceFilePath,
        fallbackSettings: settings,
        settingsBySource,
      });
      TEXTURE_FILE_ATTRIBUTES.forEach((attributeName) => {
        appendAssetValidationOutcome(summary, assetIndex, {
          sourceFilePath: context.sourceFilePath,
          referenceKind: 'texture',
          attributeName,
          rawPath: textureEl.getAttribute(attributeName),
          compilerDirectory: context.compilerDirectory,
          elementName: textureEl.getAttribute('name'),
        });
      });
    });

    collectDirectChildElements(assetEl, 'hfield').forEach((hfieldEl) => {
      const context = resolveElementReferenceContext(hfieldEl, 'hfield', {
        fallbackSourceFilePath: sourceFilePath,
        fallbackSettings: settings,
        settingsBySource,
      });
      appendAssetValidationOutcome(summary, assetIndex, {
        sourceFilePath: context.sourceFilePath,
        referenceKind: 'hfield',
        attributeName: 'file',
        rawPath: hfieldEl.getAttribute('file'),
        compilerDirectory: context.compilerDirectory,
        elementName: hfieldEl.getAttribute('name'),
      });
    });

    collectDirectChildElements(assetEl, 'model').forEach((modelEl) => {
      const context = resolveElementReferenceContext(modelEl, 'model', {
        fallbackSourceFilePath: sourceFilePath,
        fallbackSettings: settings,
        settingsBySource,
      });
      appendAssetValidationOutcome(summary, assetIndex, {
        sourceFilePath: context.sourceFilePath,
        referenceKind: 'model',
        attributeName: 'file',
        rawPath: modelEl.getAttribute('file'),
        compilerDirectory: context.compilerDirectory,
        elementName: modelEl.getAttribute('name'),
      });
    });
  });

  return summary;
}

export function validateMJCFImportExternalAssets(
  sourceFilePath: string,
  content: string,
  availableFiles: RobotFile[],
  assets: Record<string, string>,
): MJCFImportExternalAssetIssue[] {
  return inspectMJCFImportExternalAssets(sourceFilePath, content, availableFiles, assets).issues;
}
