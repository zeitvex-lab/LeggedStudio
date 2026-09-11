import * as THREE from 'three';
import { getLowestMeshZ } from '@/shared/utils';

interface ResolveUsdGroundAlignmentBaselineOptions {
  includeCollisionAsFallback?: boolean;
}

interface AlignUsdSceneRootToGroundOptions extends ResolveUsdGroundAlignmentBaselineOptions {
  lowestVisualZ?: number | null;
}

export function resolveUsdGroundAlignmentBaseline(
  root: THREE.Object3D,
  options?: ResolveUsdGroundAlignmentBaselineOptions,
): number | null {
  const includeCollisionAsFallback = options?.includeCollisionAsFallback ?? false;

  let lowestVisualZ = getLowestMeshZ(root, {
    includeInvisible: false,
    includeVisual: true,
    includeCollision: false,
  });

  if (lowestVisualZ === null && includeCollisionAsFallback) {
    lowestVisualZ = getLowestMeshZ(root, {
      includeInvisible: false,
      includeVisual: false,
      includeCollision: true,
    });
  }

  if (lowestVisualZ === null) {
    lowestVisualZ = getLowestMeshZ(root, {
      includeInvisible: true,
      includeVisual: !includeCollisionAsFallback,
      includeCollision: includeCollisionAsFallback,
    });
  }

  return lowestVisualZ;
}

export function alignUsdSceneRootToGround(
  root: THREE.Object3D,
  groundPlaneOffset = 0,
  options?: AlignUsdSceneRootToGroundOptions,
): boolean {
  const lowestVisualZ =
    options?.lowestVisualZ ??
    resolveUsdGroundAlignmentBaseline(root, {
      includeCollisionAsFallback: options?.includeCollisionAsFallback,
    });

  if (lowestVisualZ === null || lowestVisualZ === undefined) {
    return false;
  }

  root.position.z += groundPlaneOffset - lowestVisualZ;
  root.updateMatrixWorld(true);
  return true;
}
