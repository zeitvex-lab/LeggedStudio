import { getVisualGeometryEntries } from '@/core/robot';
import { cleanFilePath } from '@/core/loaders';
import type { UrdfLink, UrdfVisual } from '@/types';
import { GeometryType } from '@/types';
import type { GeometrySnapshot } from './GeometryEditor.types';

const APPROXIMATE_VISUAL_REFERENCE_STEM_SUFFIX_PATTERN =
  /(?:[_\-.](?:visual|collision|collider|mesh|model|col|vis))+$/i;

export async function yieldToNextFrame(): Promise<void> {
  await new Promise<void>((resolve) => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => resolve());
      return;
    }

    setTimeout(resolve, 0);
  });
}

export function describeAssetPath(filePath: string): { fileName: string; parentPath: string } {
  const normalizedPath = filePath.replace(/\\/g, '/');
  const pathSegments = normalizedPath.split('/');
  const fileName = pathSegments[pathSegments.length - 1] || normalizedPath;
  const parentPath = pathSegments.slice(0, -1).join('/');

  return {
    fileName,
    parentPath,
  };
}

export function createGeometrySnapshot(source: UrdfVisual): GeometrySnapshot {
  return {
    dimensions: source.dimensions
      ? {
          x: source.dimensions.x,
          y: source.dimensions.y,
          z: source.dimensions.z,
        }
      : undefined,
    origin: source.origin
      ? {
          xyz: {
            x: source.origin.xyz.x,
            y: source.origin.xyz.y,
            z: source.origin.xyz.z,
          },
          rpy: {
            r: source.origin.rpy.r,
            p: source.origin.rpy.p,
            y: source.origin.rpy.y,
          },
        }
      : undefined,
    meshPath: source.meshPath,
    assetRef: source.assetRef,
    mjcfHfield: source.mjcfHfield
      ? {
          ...source.mjcfHfield,
          size: source.mjcfHfield.size ? { ...source.mjcfHfield.size } : undefined,
          elevation: source.mjcfHfield.elevation ? [...source.mjcfHfield.elevation] : undefined,
        }
      : undefined,
    color: source.color,
  };
}

function getOriginDistanceSquared(
  left: UrdfVisual['origin'] | undefined,
  right: UrdfVisual['origin'] | undefined,
): number {
  const leftX = left?.xyz?.x ?? 0;
  const leftY = left?.xyz?.y ?? 0;
  const leftZ = left?.xyz?.z ?? 0;
  const rightX = right?.xyz?.x ?? 0;
  const rightY = right?.xyz?.y ?? 0;
  const rightZ = right?.xyz?.z ?? 0;
  const dx = leftX - rightX;
  const dy = leftY - rightY;
  const dz = leftZ - rightZ;
  return dx * dx + dy * dy + dz * dz;
}

function normalizeMeshReferenceStem(meshPath: string | undefined): string | null {
  const normalizedPath = cleanFilePath((meshPath ?? '').trim());
  if (!normalizedPath) {
    return null;
  }

  const filename = normalizedPath.split('/').pop() ?? normalizedPath;
  const lastDotIndex = filename.lastIndexOf('.');
  const stem = (lastDotIndex >= 0 ? filename.slice(0, lastDotIndex) : filename).toLowerCase();
  if (!stem) {
    return null;
  }

  let simplifiedStem = stem;
  let previousStem = '';
  while (simplifiedStem && simplifiedStem !== previousStem) {
    previousStem = simplifiedStem;
    simplifiedStem = simplifiedStem.replace(APPROXIMATE_VISUAL_REFERENCE_STEM_SUFFIX_PATTERN, '');
  }

  return simplifiedStem || stem;
}

export function resolveCollisionVisualMeshReference(
  link: UrdfLink,
  collisionObjectIndex: number,
  collisionGeometry: UrdfVisual,
): UrdfVisual | null {
  const meshEntries = getVisualGeometryEntries(link).filter(
    (entry) => entry.geometry.type === GeometryType.MESH && Boolean(entry.geometry.meshPath),
  );

  if (meshEntries.length === 0) {
    return null;
  }

  const collisionMeshStem = normalizeMeshReferenceStem(collisionGeometry.meshPath);

  const nearestEntry = meshEntries.reduce((bestEntry, entry) => {
    if (!bestEntry) {
      return entry;
    }

    const entryMeshStem = normalizeMeshReferenceStem(entry.geometry.meshPath);
    const bestMeshStem = normalizeMeshReferenceStem(bestEntry.geometry.meshPath);
    const entryStemMatched = Boolean(
      collisionMeshStem && entryMeshStem && collisionMeshStem === entryMeshStem,
    );
    const bestStemMatched = Boolean(
      collisionMeshStem && bestMeshStem && collisionMeshStem === bestMeshStem,
    );

    if (entryStemMatched !== bestStemMatched) {
      return entryStemMatched ? entry : bestEntry;
    }

    const entrySameIndex = entry.objectIndex === collisionObjectIndex;
    const bestSameIndex = bestEntry.objectIndex === collisionObjectIndex;
    if (entrySameIndex !== bestSameIndex) {
      return entrySameIndex ? entry : bestEntry;
    }

    const bestDistance = getOriginDistanceSquared(
      bestEntry.geometry.origin,
      collisionGeometry.origin,
    );
    const nextDistance = getOriginDistanceSquared(entry.geometry.origin, collisionGeometry.origin);

    if (nextDistance < bestDistance - 1e-8) {
      return entry;
    }

    if (
      Math.abs(nextDistance - bestDistance) <= 1e-8 &&
      entry.objectIndex < bestEntry.objectIndex
    ) {
      return entry;
    }

    return bestEntry;
  }, meshEntries[0] ?? null);

  return nearestEntry?.geometry ?? null;
}
