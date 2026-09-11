import * as THREE from 'three';

import { deriveObjAuthoredMaterialsFromLookup } from '@/core/loaders/objMaterialUtils';
import { syncRobotMaterialsForLinkUpdate } from '@/core/robot/materials';
import { postProcessColladaScene } from '@/core/loaders';
import {
  createSceneFromSerializedColladaData,
  parseColladaSceneData,
} from '@/core/loaders/colladaWorkerSceneData';
import { resolveImportedAssetPath } from '@/core/parsers/meshPathUtils';
import { DEFAULT_VISUAL_COLOR, GeometryType, type RobotData, type UrdfVisual } from '@/types';

import { disposeTransientObject3D } from './mjcfLoadLifecycle';

type RobotMaterialEntry = NonNullable<RobotData['materials']>[string];
type TextAssetContentLookup = ReadonlyMap<string, string>;
const MAX_REPRESENTATIVE_MESH_COLOR_CACHE_SIZE = 128;
const representativeMeshColorCache = new Map<string, string | null>();

function normalizeLookupPath(filePath: string): string {
  return filePath.replace(/\\/g, '/').trim().replace(/^\/+/, '').split('?')[0];
}

function buildTextContentSignature(content: string): string {
  let hash = 2166136261;

  for (let index = 0; index < content.length; index += 1) {
    hash ^= content.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return `${content.length}:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

function normalizeMaterialValue(value?: string | null): string | undefined {
  const trimmed = String(value || '').trim();
  return trimmed ? trimmed : undefined;
}

function rgbaUnitChannelToHex(value: number): string {
  const byte = Math.max(0, Math.min(255, Math.round(value * 255)));
  return byte.toString(16).padStart(2, '0');
}

function createTextAssetContentLookup(
  allFileContents: Record<string, string>,
): TextAssetContentLookup {
  const lookup = new Map<string, string>();

  for (const [path, content] of Object.entries(allFileContents)) {
    if (typeof content !== 'string' || content.length === 0) {
      continue;
    }

    const normalizedPath = normalizeLookupPath(path);
    if (!normalizedPath) {
      continue;
    }

    lookup.set(normalizedPath, content);
  }

  return lookup;
}

function findTextAssetContent(
  assetPath: string,
  textAssetContentLookup: TextAssetContentLookup,
): string | null {
  const normalizedAssetPath = normalizeLookupPath(assetPath);
  if (!normalizedAssetPath) {
    return null;
  }

  return textAssetContentLookup.get(normalizedAssetPath) ?? null;
}

function extractMaterialColorHex(material: THREE.Material | undefined): string | undefined {
  if (!material) {
    return undefined;
  }

  const color = (material as THREE.Material & { color?: THREE.Color }).color;
  if (!(color instanceof THREE.Color)) {
    return undefined;
  }

  return `#${color.getHexString()}`;
}

function addColorWeight(
  colorWeights: Map<string, number>,
  color: string | undefined,
  weight: number,
): void {
  if (!color || !Number.isFinite(weight) || weight <= 0) {
    return;
  }

  colorWeights.set(color, (colorWeights.get(color) ?? 0) + weight);
}

function getRepresentativeMeshColor(object: THREE.Object3D): string | null {
  const colorWeights = new Map<string, number>();

  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) {
      return;
    }

    const geometry = mesh.geometry as THREE.BufferGeometry | undefined;
    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : mesh.material
        ? [mesh.material]
        : [];

    if (materials.length === 0) {
      return;
    }

    const indexCount = geometry?.index?.count ?? 0;
    const vertexCount = geometry?.attributes?.position?.count ?? 0;
    const defaultWeight = Math.max(indexCount, vertexCount, 1);

    if (materials.length === 1) {
      addColorWeight(colorWeights, extractMaterialColorHex(materials[0]), defaultWeight);
      return;
    }

    const groupWeights = new Array<number>(materials.length).fill(0);
    if (geometry?.groups?.length) {
      geometry.groups.forEach((group) => {
        const materialIndex = group.materialIndex;
        if (
          materialIndex !== undefined &&
          materialIndex >= 0 &&
          materialIndex < groupWeights.length
        ) {
          groupWeights[materialIndex] += Math.max(group.count, 1);
        }
      });
    }

    const fallbackWeight = defaultWeight / materials.length;
    materials.forEach((material, index) => {
      addColorWeight(
        colorWeights,
        extractMaterialColorHex(material),
        groupWeights[index] > 0 ? groupWeights[index] : fallbackWeight,
      );
    });
  });

  let representativeColor: string | null = null;
  let bestWeight = -1;

  colorWeights.forEach((weight, color) => {
    if (weight > bestWeight) {
      bestWeight = weight;
      representativeColor = color;
    }
  });

  return representativeColor;
}

function parseObjMaterialLibraries(content: string): string[] {
  const materialLibraries: string[] = [];
  const matches = content.matchAll(/^[ \t]*mtllib[ \t]+(.+)$/gim);
  for (const match of matches) {
    const rawValue = String(match[1] || '').trim();
    if (!rawValue) {
      continue;
    }

    materialLibraries.push(...rawValue.split(/\s+/).filter(Boolean));
  }

  return materialLibraries;
}

function buildRepresentativeMeshColorCacheKey(
  normalizedMeshPath: string,
  meshContent: string,
  textAssetContentLookup: TextAssetContentLookup,
): string {
  const extension = normalizedMeshPath.split('.').pop()?.toLowerCase() ?? 'unknown';
  const keyParts = [extension, normalizedMeshPath, buildTextContentSignature(meshContent)];

  if (extension === 'obj') {
    parseObjMaterialLibraries(meshContent).forEach((materialLibrary) => {
      const resolvedMaterialPath = normalizeLookupPath(
        resolveImportedAssetPath(materialLibrary, normalizedMeshPath),
      );
      const materialContent = findTextAssetContent(resolvedMaterialPath, textAssetContentLookup);
      keyParts.push(`${resolvedMaterialPath}:${buildTextContentSignature(materialContent ?? '')}`);
    });
  }

  return keyParts.join('|');
}

function readRepresentativeMeshColorCache(cacheKey: string): string | null | undefined {
  const cachedColor = representativeMeshColorCache.get(cacheKey);
  if (cachedColor === undefined) {
    return undefined;
  }

  representativeMeshColorCache.delete(cacheKey);
  representativeMeshColorCache.set(cacheKey, cachedColor);
  return cachedColor;
}

function writeRepresentativeMeshColorCache(cacheKey: string, color: string | null): void {
  if (representativeMeshColorCache.has(cacheKey)) {
    representativeMeshColorCache.delete(cacheKey);
  }

  representativeMeshColorCache.set(cacheKey, color);

  while (representativeMeshColorCache.size > MAX_REPRESENTATIVE_MESH_COLOR_CACHE_SIZE) {
    const oldestKey = representativeMeshColorCache.keys().next().value;
    if (oldestKey === undefined) {
      break;
    }

    representativeMeshColorCache.delete(oldestKey);
  }
}

function parseObjVertexReferenceIndex(token: string, vertexCount: number): number | null {
  const rawIndex = Number.parseInt(token.split('/')[0] || '', 10);
  if (!Number.isFinite(rawIndex) || rawIndex === 0) {
    return null;
  }

  const resolvedIndex = rawIndex > 0 ? rawIndex - 1 : vertexCount + rawIndex;
  return resolvedIndex >= 0 && resolvedIndex < vertexCount ? resolvedIndex : null;
}

function parseObjVertexColorHex(line: string): string | null {
  const tokens = line.trim().split(/\s+/);
  if (tokens.length < 7 || tokens[0] !== 'v') {
    return null;
  }

  const channels = tokens.slice(4, 7).map((value) => Number.parseFloat(value));
  if (!channels.every((value) => Number.isFinite(value))) {
    return null;
  }

  return `#${channels.map(rgbaUnitChannelToHex).join('')}`;
}

function buildObjMaterialColorLookup(
  meshPath: string,
  textAssetContentLookup: TextAssetContentLookup,
): Map<string, string> {
  const materialColors = new Map<string, string>();

  deriveObjAuthoredMaterialsFromLookup(meshPath, textAssetContentLookup).forEach((material) => {
    const name = normalizeMaterialValue(material.name);
    const color =
      normalizeMaterialValue(material.color) ??
      (normalizeMaterialValue(material.texture) ? '#ffffff' : undefined);
    if (name && color) {
      materialColors.set(name, color);
    }
  });

  return materialColors;
}

function addObjReferenceVertexColors(
  colorWeights: Map<string, number>,
  vertexColors: Array<string | null>,
  references: string[],
  weightMultiplier = 1,
): void {
  references.forEach((reference) => {
    const vertexIndex = parseObjVertexReferenceIndex(reference, vertexColors.length);
    if (vertexIndex === null) {
      return;
    }

    addColorWeight(colorWeights, vertexColors[vertexIndex] ?? undefined, weightMultiplier);
  });
}

function getDominantWeightedColor(colorWeights: Map<string, number>): string | null {
  let representativeColor: string | null = null;
  let bestWeight = -1;

  colorWeights.forEach((weight, color) => {
    if (weight > bestWeight) {
      bestWeight = weight;
      representativeColor = color;
    }
  });

  return representativeColor;
}

function deriveRepresentativeObjColorFromTextContent(
  meshPath: string,
  meshContent: string,
  textAssetContentLookup: TextAssetContentLookup,
): string | null {
  const materialColors = buildObjMaterialColorLookup(meshPath, textAssetContentLookup);
  const vertexColors: Array<string | null> = [];
  const colorWeights = new Map<string, number>();
  let currentMaterialName = '';

  meshContent.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      return;
    }

    if (trimmed.startsWith('v ')) {
      vertexColors.push(parseObjVertexColorHex(trimmed));
      return;
    }

    if (trimmed.startsWith('usemtl ')) {
      currentMaterialName = trimmed.slice(7).trim();
      return;
    }

    const tokens = trimmed.split(/\s+/);
    const directive = tokens[0];
    const references = tokens.slice(1);
    if (references.length === 0 || (directive !== 'f' && directive !== 'l' && directive !== 'p')) {
      return;
    }

    const materialColor = materialColors.get(currentMaterialName);
    const primitiveWeight =
      directive === 'f'
        ? Math.max(references.length - 2, 1) * 3
        : directive === 'l'
          ? Math.max(references.length - 1, 1) * 2
          : references.length;

    if (materialColor) {
      addColorWeight(colorWeights, materialColor, primitiveWeight);
      return;
    }

    if (directive === 'f' && references.length >= 3) {
      for (let index = 1; index + 1 < references.length; index += 1) {
        addObjReferenceVertexColors(colorWeights, vertexColors, [
          references[0]!,
          references[index]!,
          references[index + 1]!,
        ]);
      }
      return;
    }

    addObjReferenceVertexColors(colorWeights, vertexColors, references);
  });

  return getDominantWeightedColor(colorWeights);
}

function deriveRepresentativeMeshColor(
  meshPath: string,
  textAssetContentLookup: TextAssetContentLookup,
  colorCache: Map<string, string | null>,
): string | null {
  const normalizedMeshPath = normalizeLookupPath(meshPath);
  const cachedColor = colorCache.get(normalizedMeshPath);
  if (cachedColor !== undefined) {
    return cachedColor;
  }

  const meshContent = findTextAssetContent(normalizedMeshPath, textAssetContentLookup);
  if (!meshContent) {
    colorCache.set(normalizedMeshPath, null);
    return null;
  }

  const cacheKey = buildRepresentativeMeshColorCacheKey(
    normalizedMeshPath,
    meshContent,
    textAssetContentLookup,
  );
  const cachedRepresentativeColor = readRepresentativeMeshColorCache(cacheKey);
  if (cachedRepresentativeColor !== undefined) {
    colorCache.set(normalizedMeshPath, cachedRepresentativeColor);
    return cachedRepresentativeColor;
  }

  const extension = normalizedMeshPath.split('.').pop()?.toLowerCase();
  let root: THREE.Object3D | null = null;

  try {
    let representativeColor: string | null = null;
    switch (extension) {
      case 'dae':
        root = createSceneFromSerializedColladaData(
          parseColladaSceneData(meshContent, normalizedMeshPath),
        );
        postProcessColladaScene(root);
        representativeColor = getRepresentativeMeshColor(root);
        break;
      case 'obj':
        representativeColor = deriveRepresentativeObjColorFromTextContent(
          normalizedMeshPath,
          meshContent,
          textAssetContentLookup,
        );
        break;
      default:
        colorCache.set(normalizedMeshPath, null);
        return null;
    }

    writeRepresentativeMeshColorCache(cacheKey, representativeColor);
    colorCache.set(normalizedMeshPath, representativeColor);
    return representativeColor;
  } catch (error) {
    console.warn(
      `[MJCFImport] Failed to derive representative mesh color from "${normalizedMeshPath}".`,
      error,
    );
    writeRepresentativeMeshColorCache(cacheKey, null);
    colorCache.set(normalizedMeshPath, null);
    return null;
  } finally {
    disposeTransientObject3D(root);
  }
}

function geometryHasExplicitMaterialOverride(
  geometry: Pick<UrdfVisual, 'authoredMaterials'>,
): boolean {
  return (
    geometry.authoredMaterials?.some((material) =>
      Boolean(normalizeMaterialValue(material.color || material.texture)),
    ) ?? false
  );
}

function shouldBackfillGeometryColor(
  geometry: UrdfVisual,
  existingMaterial: RobotMaterialEntry | undefined,
): boolean {
  return (
    geometry.type === GeometryType.MESH &&
    Boolean(geometry.meshPath) &&
    normalizeMaterialValue(geometry.color) === DEFAULT_VISUAL_COLOR &&
    !geometryHasExplicitMaterialOverride(geometry) &&
    !normalizeMaterialValue(existingMaterial?.color) &&
    !normalizeMaterialValue(existingMaterial?.texture)
  );
}

function syncGeometryMeshTextMaterials(
  geometry: UrdfVisual,
  textAssetContentLookup: TextAssetContentLookup,
  colorCache: Map<string, string | null>,
  existingMaterial?: RobotMaterialEntry,
): UrdfVisual {
  if (!shouldBackfillGeometryColor(geometry, existingMaterial)) {
    return geometry;
  }

  const normalizedMeshPath = normalizeLookupPath(geometry.meshPath!);
  if (normalizedMeshPath.toLowerCase().endsWith('.obj')) {
    const authoredMaterials = deriveObjAuthoredMaterialsFromLookup(
      normalizedMeshPath,
      textAssetContentLookup,
    );
    if (authoredMaterials.length > 1) {
      return {
        ...geometry,
        color: '',
        authoredMaterials,
      };
    }

    if (authoredMaterials.length === 1) {
      const [primaryMaterial] = authoredMaterials;
      const representativeColor =
        normalizeMaterialValue(primaryMaterial?.color) ??
        (normalizeMaterialValue(primaryMaterial?.texture) ? '#ffffff' : undefined) ??
        deriveRepresentativeMeshColor(normalizedMeshPath, textAssetContentLookup, colorCache) ??
        undefined;

      return {
        ...geometry,
        ...(representativeColor ? { color: representativeColor } : {}),
        authoredMaterials,
      };
    }
  }

  const representativeColor = deriveRepresentativeMeshColor(
    normalizedMeshPath,
    textAssetContentLookup,
    colorCache,
  );
  if (!representativeColor) {
    return geometry;
  }

  return {
    ...geometry,
    color: representativeColor,
  };
}

export function syncMjcfMeshTextMaterialColors(
  robotData: RobotData,
  allFileContents: Record<string, string> = {},
): RobotData {
  if (Object.keys(allFileContents).length === 0) {
    return robotData;
  }

  const colorCache = new Map<string, string | null>();
  const textAssetContentLookup = createTextAssetContentLookup(allFileContents);
  let linksChanged = false;
  let nextMaterials = robotData.materials;

  const nextLinks = Object.fromEntries(
    Object.entries(robotData.links).map(([linkId, link]) => {
      const existingMaterial = robotData.materials?.[link.id] ?? robotData.materials?.[link.name];
      const nextVisual = syncGeometryMeshTextMaterials(
        link.visual,
        textAssetContentLookup,
        colorCache,
        existingMaterial,
      );
      if (nextVisual === link.visual) {
        return [linkId, link];
      }

      linksChanged = true;
      const nextLink = {
        ...link,
        visual: nextVisual,
      };
      nextMaterials = syncRobotMaterialsForLinkUpdate(nextMaterials, nextLink, link);

      return [linkId, nextLink];
    }),
  ) as RobotData['links'];

  if (!linksChanged) {
    return robotData;
  }

  return {
    ...robotData,
    links: nextLinks,
    ...(nextMaterials ? { materials: nextMaterials } : {}),
  };
}
