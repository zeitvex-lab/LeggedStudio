import * as THREE from 'three';
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader.js';

import { buildAssetIndex, findAssetByIndex, type AssetIndex } from '@/core/loaders';
import { postProcessColladaScene } from '@/core/loaders';
import {
  createSceneFromSerializedColladaData,
  parseColladaSceneData,
} from '@/core/loaders/colladaWorkerSceneData';
import { getSourceFileDirectory } from './meshPathUtils';
import type { UrdfVisualMaterial } from '@/types';

interface TextAssetLookup {
  assetIndex: AssetIndex;
  textContents: Map<string, string>;
  meshAuthoredMaterialsCache: Map<string, UrdfVisualMaterial[]>;
}

function normalizeLookupPath(filePath: string): string {
  return filePath.replace(/\\/g, '/').trim().replace(/^\/+/, '').split('?')[0];
}

function normalizeMaterialValue(value?: string | null): string | undefined {
  const trimmed = String(value || '').trim();
  return trimmed ? trimmed : undefined;
}

function createTextAssetLookup(
  allFileContents: Record<string, string>,
  assetPaths: Iterable<string> = [],
): TextAssetLookup {
  const normalizedAssetMap: Record<string, string> = {};
  const textContents = new Map<string, string>();

  for (const assetPath of assetPaths) {
    const normalizedPath = normalizeLookupPath(assetPath);
    if (!normalizedPath) {
      continue;
    }

    normalizedAssetMap[normalizedPath] = normalizedPath;
  }

  for (const [assetPath, content] of Object.entries(allFileContents)) {
    const normalizedPath = normalizeLookupPath(assetPath);
    if (!normalizedPath) {
      continue;
    }

    normalizedAssetMap[normalizedPath] = normalizedPath;
    if (typeof content === 'string') {
      textContents.set(normalizedPath, content);
    }
  }

  return {
    assetIndex: buildAssetIndex(normalizedAssetMap),
    textContents,
    meshAuthoredMaterialsCache: new Map<string, UrdfVisualMaterial[]>(),
  };
}

const EMPTY_TEXT_CONTENTS_TOKEN = {} as const;
const EMPTY_ASSET_PATHS_TOKEN = {} as const;
const textAssetLookupCache = new WeakMap<object, WeakMap<object, TextAssetLookup>>();

function getTextAssetLookup(
  allFileContents: Record<string, string>,
  assetPaths: Iterable<string> | undefined,
): TextAssetLookup {
  const fileKey = (allFileContents ?? EMPTY_TEXT_CONTENTS_TOKEN) as unknown as object;
  const assetKey =
    assetPaths && (typeof assetPaths === 'object' || typeof assetPaths === 'function')
      ? (assetPaths as unknown as object)
      : (EMPTY_ASSET_PATHS_TOKEN as unknown as object);

  const existingAssetMap = textAssetLookupCache.get(fileKey);
  if (existingAssetMap) {
    const cached = existingAssetMap.get(assetKey);
    if (cached) {
      return cached;
    }
  }

  const lookup = createTextAssetLookup(allFileContents, assetPaths ?? []);
  const byAssets = existingAssetMap ?? new WeakMap<object, TextAssetLookup>();
  byAssets.set(assetKey, lookup);
  if (!existingAssetMap) {
    textAssetLookupCache.set(fileKey, byAssets);
  }

  return lookup;
}

function resolveAssetPath(
  assetPath: string,
  lookup: TextAssetLookup,
  sourcePath?: string | null,
): string | null {
  const normalizedAssetPath = normalizeMaterialValue(assetPath);
  if (!normalizedAssetPath) {
    return null;
  }

  const resolvedPath = findAssetByIndex(
    normalizedAssetPath,
    lookup.assetIndex,
    getSourceFileDirectory(sourcePath),
  );

  return resolvedPath ? normalizeLookupPath(resolvedPath) : null;
}

function resolveTextAssetContent(
  assetPath: string,
  lookup: TextAssetLookup,
  sourcePath?: string | null,
): { path: string; content: string } | null {
  const resolvedPath = resolveAssetPath(assetPath, lookup, sourcePath);
  if (!resolvedPath) {
    return null;
  }

  const content = lookup.textContents.get(resolvedPath);
  if (!content) {
    return null;
  }

  return {
    path: resolvedPath,
    content,
  };
}

function rgbaToHex(channels: unknown): string | undefined {
  if (!Array.isArray(channels) || channels.length < 3) {
    return undefined;
  }

  const [red, green, blue] = channels
    .slice(0, 3)
    .map((value) => Number(value))
    .map((value) => (Number.isFinite(value) ? value : Number.NaN));

  if (![red, green, blue].every(Number.isFinite)) {
    return undefined;
  }

  const toByte = (value: number) => Math.max(0, Math.min(255, Math.round(value * 255)));
  return `#${[toByte(red), toByte(green), toByte(blue)]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('')}`;
}

function normalizeAuthoredMaterial(material: UrdfVisualMaterial | null): UrdfVisualMaterial | null {
  if (!material) {
    return null;
  }

  const name = normalizeMaterialValue(material.name);
  const color = normalizeMaterialValue(material.color);
  const texture = normalizeMaterialValue(material.texture);
  if (!name && !color && !texture) {
    return null;
  }

  return {
    ...(name ? { name } : {}),
    ...(color ? { color } : {}),
    ...(texture ? { texture } : {}),
  };
}

function disposeTransientObject3D(root: THREE.Object3D | null | undefined): void {
  if (!root) {
    return;
  }

  if (root.parent) {
    root.parent.remove(root);
  }

  const disposedMaterials = new Set<THREE.Material>();
  const disposedSkeletons = new Set<THREE.Skeleton>();
  const disposedTextures = new Set<THREE.Texture>();

  root.traverse((child) => {
    const skinnedMesh = child as THREE.SkinnedMesh;
    if (
      skinnedMesh.isSkinnedMesh &&
      skinnedMesh.skeleton &&
      !disposedSkeletons.has(skinnedMesh.skeleton)
    ) {
      disposedSkeletons.add(skinnedMesh.skeleton);
      skinnedMesh.skeleton.dispose?.();
    }

    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) {
      return;
    }

    mesh.geometry?.dispose?.();

    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of materials) {
      if (!material || disposedMaterials.has(material)) {
        continue;
      }

      for (const value of Object.values(material as unknown as Record<string, unknown>)) {
        if (!(value instanceof THREE.Texture) || disposedTextures.has(value)) {
          continue;
        }

        disposedTextures.add(value);
        value.dispose?.();
      }

      material.dispose?.();
      disposedMaterials.add(material);
    }
  });

  root.clear();
}

function extractMaterialColorHex(material: THREE.Material | undefined): string | undefined {
  const color = (material as THREE.Material & { color?: THREE.Color })?.color;
  if (!(color instanceof THREE.Color)) {
    return undefined;
  }

  return `#${color.getHexString()}`;
}

function resolveRuntimeTexturePath(
  material: THREE.Material | undefined,
  lookup: TextAssetLookup,
  sourcePath?: string | null,
): string | undefined {
  const texture = (material as THREE.Material & { map?: THREE.Texture })?.map;
  if (!(texture instanceof THREE.Texture)) {
    return undefined;
  }

  const textureSourceData = texture.source?.data as
    | { currentSrc?: string; src?: string }
    | undefined;
  const textureImage = (
    texture as THREE.Texture & {
      image?: { currentSrc?: string; src?: string };
    }
  ).image;
  const candidates = [
    textureSourceData?.currentSrc,
    textureSourceData?.src,
    textureImage?.currentSrc,
    textureImage?.src,
  ];

  for (const candidate of candidates) {
    const resolvedPath = resolveAssetPath(String(candidate || ''), lookup, sourcePath);
    if (resolvedPath) {
      return resolvedPath;
    }
  }

  return undefined;
}

export function parseObjMaterialLibraries(content: string): string[] {
  const materialLibraries: string[] = [];
  const matches = content.matchAll(/^[ \t]*mtllib[ \t]+(.+)$/gim);
  for (const match of matches) {
    const rawValue = String(match[1] || '').trim();
    if (!rawValue) {
      continue;
    }

    materialLibraries.push(rawValue);
  }

  return materialLibraries;
}

function parseMtlAuthoredMaterials(
  mtlContent: string,
  mtlPath: string,
  lookup: TextAssetLookup,
): UrdfVisualMaterial[] {
  const materialCreator = new MTLLoader().parse(
    mtlContent,
    getSourceFileDirectory(mtlPath),
  ) as unknown as {
    materialsInfo?: Record<string, Record<string, unknown>>;
  };
  const materialsInfo = materialCreator.materialsInfo ?? {};

  return Object.entries(materialsInfo)
    .map(([materialName, materialInfo]) =>
      normalizeAuthoredMaterial({
        name: materialName,
        color: rgbaToHex(materialInfo.kd ?? materialInfo.ka),
        texture:
          resolveAssetPath(
            String(materialInfo.map_kd || materialInfo.map_ka || ''),
            lookup,
            mtlPath,
          ) || undefined,
      }),
    )
    .filter((material): material is UrdfVisualMaterial => Boolean(material));
}

function parseColladaAuthoredMaterials(
  colladaContent: string,
  colladaPath: string,
  lookup: TextAssetLookup,
): UrdfVisualMaterial[] {
  let root: THREE.Object3D | null = null;

  try {
    root = createSceneFromSerializedColladaData(parseColladaSceneData(colladaContent, colladaPath));
    postProcessColladaScene(root);

    const authoredMaterials: UrdfVisualMaterial[] = [];
    const seenMaterials = new Set<string>();

    root.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh) {
        return;
      }

      const materials = Array.isArray(mesh.material)
        ? mesh.material
        : mesh.material
          ? [mesh.material]
          : [];

      materials.forEach((material) => {
        const normalized = normalizeAuthoredMaterial({
          name: normalizeMaterialValue(material?.name),
          color: extractMaterialColorHex(material),
          texture: resolveRuntimeTexturePath(material, lookup, colladaPath),
        });
        if (!normalized) {
          return;
        }

        const materialKey = JSON.stringify(normalized);
        if (seenMaterials.has(materialKey)) {
          return;
        }

        seenMaterials.add(materialKey);
        authoredMaterials.push(normalized);
      });
    });

    return authoredMaterials;
  } catch {
    return [];
  } finally {
    disposeTransientObject3D(root);
  }
}

export function resolveMeshTextAuthoredMaterials(
  meshPath: string | null | undefined,
  options: {
    allFileContents?: Record<string, string>;
    assetPaths?: Iterable<string>;
  } = {},
): UrdfVisualMaterial[] {
  const normalizedMeshPath = normalizeMaterialValue(meshPath);
  const normalizedExtension = normalizedMeshPath?.split('.').pop()?.toLowerCase();
  if (!normalizedMeshPath || (normalizedExtension !== 'obj' && normalizedExtension !== 'dae')) {
    return [];
  }

  const lookup = getTextAssetLookup(options.allFileContents ?? {}, options.assetPaths);
  const meshAsset = resolveTextAssetContent(normalizedMeshPath, lookup, normalizedMeshPath);
  if (!meshAsset) {
    return [];
  }

  if (lookup.meshAuthoredMaterialsCache.has(meshAsset.path)) {
    return lookup.meshAuthoredMaterialsCache.get(meshAsset.path) ?? [];
  }

  if (normalizedExtension === 'dae') {
    const authoredMaterials = parseColladaAuthoredMaterials(
      meshAsset.content,
      meshAsset.path,
      lookup,
    );
    lookup.meshAuthoredMaterialsCache.set(meshAsset.path, authoredMaterials);
    return authoredMaterials;
  }

  const authoredMaterials: UrdfVisualMaterial[] = [];
  for (const materialLibrary of parseObjMaterialLibraries(meshAsset.content)) {
    const mtlAsset = resolveTextAssetContent(materialLibrary, lookup, meshAsset.path);
    if (!mtlAsset) {
      continue;
    }

    authoredMaterials.push(...parseMtlAuthoredMaterials(mtlAsset.content, mtlAsset.path, lookup));
  }

  const dedupedMaterials = new Map<string, UrdfVisualMaterial>();
  for (const material of authoredMaterials) {
    const normalized = normalizeAuthoredMaterial(material);
    if (!normalized) {
      continue;
    }

    const key = JSON.stringify(normalized);
    if (!dedupedMaterials.has(key)) {
      dedupedMaterials.set(key, normalized);
    }
  }

  const result = [...dedupedMaterials.values()];
  lookup.meshAuthoredMaterialsCache.set(meshAsset.path, result);
  return result;
}
