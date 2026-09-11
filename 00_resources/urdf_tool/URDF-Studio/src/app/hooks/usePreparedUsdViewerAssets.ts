import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { resolveImportedAssetPath } from '@/core/parsers/meshPathUtils';
import {
  buildAssemblyProjectedAssetAliases,
  resolveAssemblyComponentResourcePath,
  resolveAssemblySceneRenderStrategy,
  type AssemblySceneRenderStrategy,
} from '@/core/robot';
import type { AssemblyState, RobotFile } from '@/types';

interface PreparedUsdViewerAssetDescriptor {
  assetPath: string;
  blob: Blob;
  cacheKey: string;
}

interface UsePreparedUsdViewerAssetsOptions {
  assemblyState: AssemblyState | null;
  assets: Record<string, string>;
  availableFiles: RobotFile[];
  additionalSourceFiles?: RobotFile[];
  preparedExportCaches: Record<string, { meshFiles?: Record<string, Blob> } | null>;
  getUsdPreparedExportCache: (path: string) => { meshFiles?: Record<string, Blob> } | null;
}

interface PreparedViewerAssetEntry {
  assetPath: string;
  blob: Blob;
  url: string;
}

const EMPTY_ADDITIONAL_SOURCE_FILES: RobotFile[] = [];

function preparedAssetMapsEqual(
  left: Readonly<Record<string, string>>,
  right: Readonly<Record<string, string>>,
): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key) => left[key] === right[key]);
}

export function buildProjectedAssemblyViewerAssetAliases({
  assemblyState,
  assets,
}: {
  assemblyState: AssemblyState | null;
  assets: Record<string, string>;
}): Record<string, string> {
  return assemblyState ? buildAssemblyProjectedAssetAliases({ assembly: assemblyState, assets }) : {};
}

function appendPreparedUsdViewerAssetDescriptors(
  descriptors: PreparedUsdViewerAssetDescriptor[],
  sourceFile: RobotFile,
  getUsdPreparedExportCache: UsePreparedUsdViewerAssetsOptions['getUsdPreparedExportCache'],
  componentProjection?: {
    componentId: string;
    renderStrategy: AssemblySceneRenderStrategy;
  },
): void {
  if (sourceFile.format !== 'usd') {
    return;
  }

  const preparedCache = getUsdPreparedExportCache(sourceFile.name);
  if (!preparedCache?.meshFiles) {
    return;
  }

  Object.entries(preparedCache.meshFiles).forEach(([meshPath, blob]) => {
    const assetPath = componentProjection?.renderStrategy === 'assembled-scene'
      ? resolveAssemblyComponentResourcePath({
          componentId: componentProjection.componentId,
          sourceFile: sourceFile.name,
          resourcePath: meshPath,
          renderStrategy: 'assembled-scene',
        })
      : resolveImportedAssetPath(meshPath, sourceFile.name);
    if (!assetPath) {
      return;
    }

    descriptors.push({
      assetPath,
      blob,
      cacheKey: componentProjection
        ? `${componentProjection.componentId}::${sourceFile.name}::${meshPath}`
        : `${sourceFile.name}::${meshPath}`,
    });
  });
}

export function buildPreparedUsdViewerAssetDescriptors({
  assemblyState,
  availableFiles,
  additionalSourceFiles = [],
  getUsdPreparedExportCache,
}: Omit<
  UsePreparedUsdViewerAssetsOptions,
  'assets' | 'preparedExportCaches'
>): PreparedUsdViewerAssetDescriptor[] {
  const availableFilesByPath = new Map(availableFiles.map((file) => [file.name, file] as const));
  const assemblySourcePaths = new Set<string>();
  const descriptors: PreparedUsdViewerAssetDescriptor[] = [];
  let assemblyRenderStrategy: AssemblySceneRenderStrategy | null = null;

  if (assemblyState) {
    const renderStrategy = resolveAssemblySceneRenderStrategy(assemblyState);
    assemblyRenderStrategy = renderStrategy;
    Object.values(assemblyState.components).forEach((component) => {
      if (component.visible === false) {
        return;
      }

      if (!component.sourceFile) return;
      const sourceFile = availableFilesByPath.get(component.sourceFile);
      if (sourceFile?.format === 'usd') {
        assemblySourcePaths.add(sourceFile.name);
        appendPreparedUsdViewerAssetDescriptors(
          descriptors,
          sourceFile,
          getUsdPreparedExportCache,
          { componentId: component.id, renderStrategy },
        );
      }
    });
  }

  additionalSourceFiles.forEach((sourceFile) => {
    if (
      sourceFile?.format !== 'usd'
      || (
        assemblyRenderStrategy !== 'assembled-scene'
        && assemblySourcePaths.has(sourceFile.name)
      )
    ) {
      return;
    }
    appendPreparedUsdViewerAssetDescriptors(descriptors, sourceFile, getUsdPreparedExportCache);
  });

  return descriptors;
}

export function usePreparedUsdViewerAssets({
  assemblyState,
  assets,
  availableFiles,
  additionalSourceFiles = EMPTY_ADDITIONAL_SOURCE_FILES,
  preparedExportCaches,
  getUsdPreparedExportCache,
}: UsePreparedUsdViewerAssetsOptions): Record<string, string> {
  const preparedAssetEntries = useMemo(
    () =>
      buildPreparedUsdViewerAssetDescriptors({
        assemblyState,
        availableFiles,
        additionalSourceFiles,
        getUsdPreparedExportCache,
      }),
    [
      additionalSourceFiles,
      assemblyState,
      availableFiles,
      getUsdPreparedExportCache,
      preparedExportCaches,
    ],
  );
  const projectedAssetAliases = useMemo(
    () => buildProjectedAssemblyViewerAssetAliases({ assemblyState, assets }),
    [assemblyState, assets],
  );

  const preparedAssetRegistryRef = useRef<Map<string, PreparedViewerAssetEntry>>(new Map());
  const [preparedAssets, setPreparedAssets] = useState<Record<string, string>>({});

  useLayoutEffect(() => {
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
      setPreparedAssets({});
      return;
    }

    const previousRegistry = preparedAssetRegistryRef.current;
    const nextRegistry = new Map<string, PreparedViewerAssetEntry>();
    const nextPreparedAssets: Record<string, string> = {};

    preparedAssetEntries.forEach((entry) => {
      const existing = previousRegistry.get(entry.cacheKey);
      if (existing && existing.blob === entry.blob && existing.assetPath === entry.assetPath) {
        nextRegistry.set(entry.cacheKey, existing);
        nextPreparedAssets[entry.assetPath] = existing.url;
        return;
      }

      if (existing) {
        URL.revokeObjectURL(existing.url);
      }

      const nextEntry: PreparedViewerAssetEntry = {
        assetPath: entry.assetPath,
        blob: entry.blob,
        url: URL.createObjectURL(entry.blob),
      };
      nextRegistry.set(entry.cacheKey, nextEntry);
      nextPreparedAssets[entry.assetPath] = nextEntry.url;
    });

    previousRegistry.forEach((entry, key) => {
      if (!nextRegistry.has(key)) {
        URL.revokeObjectURL(entry.url);
      }
    });

    preparedAssetRegistryRef.current = nextRegistry;
    setPreparedAssets((current) =>
      preparedAssetMapsEqual(current, nextPreparedAssets) ? current : nextPreparedAssets
    );
  }, [preparedAssetEntries]);

  useEffect(
    () => () => {
      preparedAssetRegistryRef.current.forEach((entry) => {
        URL.revokeObjectURL(entry.url);
      });
      preparedAssetRegistryRef.current.clear();
    },
    [],
  );

  return useMemo(
    () => (
      Object.keys(preparedAssets).length === 0 && Object.keys(projectedAssetAliases).length === 0
        ? assets
        : { ...assets, ...projectedAssetAliases, ...preparedAssets }
    ),
    [assets, preparedAssets, projectedAssetAliases],
  );
}
