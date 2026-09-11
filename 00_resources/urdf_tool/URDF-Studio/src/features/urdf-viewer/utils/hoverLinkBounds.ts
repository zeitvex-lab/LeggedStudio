import * as THREE from 'three';

const DEFAULT_MIN_PADDING = 0.001;
const DEFAULT_PADDING_RATIO = 0.08;
const DEFAULT_MIN_PROJECTED_PADDING_PX = 2.5;
// Expanded hover bounds are only meant to help tiny links that are hard to
// pick exactly. Once a link occupies roughly a fingertip-sized area on screen,
// the fallback becomes visible as a hover offset.
const DEFAULT_MAX_PROJECTED_SIZE_PX = 44;
const DEFAULT_MAX_POINTER_DISTANCE_PX = 3;

export interface HoverBoundsCandidate<TMeta> {
  mesh: THREE.Mesh;
  meta: TMeta;
}

export interface HoverMatch<TMeta> {
  meta: TMeta;
  distance: number;
  padding?: number;
}

export interface ResolvedHoverMatch<TMeta> {
  match: HoverMatch<TMeta>;
  source: 'exact' | 'bounds';
}

interface HoverBoundsOptions {
  minPadding?: number;
  paddingRatio?: number;
  minProjectedPaddingPx?: number;
  camera?: THREE.Camera | null;
  viewportWidth?: number;
  viewportHeight?: number;
  maxProjectedSizePx?: number;
  pointerScreenX?: number;
  pointerScreenY?: number;
  maxPointerDistancePx?: number;
}

interface ResolvePreferredHoverMatchOptions<TMeta> {
  exactMatch: HoverMatch<TMeta> | null;
  ray: THREE.Ray;
  candidates: Iterable<HoverBoundsCandidate<TMeta>>;
  getLinkKey: (meta: TMeta) => string;
  boundsOptions?: HoverBoundsOptions;
}

const pooledExpandedBounds = new THREE.Box3();
const pooledLocalHitPoint = new THREE.Vector3();
const pooledWorldHitPoint = new THREE.Vector3();
const pooledBoundsSize = new THREE.Vector3();
const projectedBoundsCorners = Array.from({ length: 8 }, () => new THREE.Vector3());
const projectedBoundsCorner = new THREE.Vector3();
const pooledWorldPosition = new THREE.Vector3();
const pooledWorldQuaternion = new THREE.Quaternion();
const pooledWorldScale = new THREE.Vector3();
const pooledLocalPaddingVector = new THREE.Vector3();
const pooledInverseMatrix = new THREE.Matrix4();
const pooledLocalRay = new THREE.Ray();

function measureProjectedBoundsRectPx(
  bounds: THREE.Box3,
  matrixWorld: THREE.Matrix4,
  camera: THREE.Camera,
  viewportWidth: number,
  viewportHeight: number,
): { minX: number; maxX: number; minY: number; maxY: number } | null {
  if (!Number.isFinite(viewportWidth) || !Number.isFinite(viewportHeight) || viewportWidth <= 0 || viewportHeight <= 0) {
    return null;
  }

  const min = bounds.min;
  const max = bounds.max;
  const corners = projectedBoundsCorners;

  corners[0].set(min.x, min.y, min.z).applyMatrix4(matrixWorld);
  corners[1].set(min.x, min.y, max.z).applyMatrix4(matrixWorld);
  corners[2].set(min.x, max.y, min.z).applyMatrix4(matrixWorld);
  corners[3].set(min.x, max.y, max.z).applyMatrix4(matrixWorld);
  corners[4].set(max.x, min.y, min.z).applyMatrix4(matrixWorld);
  corners[5].set(max.x, min.y, max.z).applyMatrix4(matrixWorld);
  corners[6].set(max.x, max.y, min.z).applyMatrix4(matrixWorld);
  corners[7].set(max.x, max.y, max.z).applyMatrix4(matrixWorld);

  let minScreenX = Infinity;
  let maxScreenX = -Infinity;
  let minScreenY = Infinity;
  let maxScreenY = -Infinity;
  let projectedCornerCount = 0;

  for (const corner of corners) {
    projectedBoundsCorner.copy(corner).project(camera);
    if (
      !Number.isFinite(projectedBoundsCorner.x)
      || !Number.isFinite(projectedBoundsCorner.y)
      || !Number.isFinite(projectedBoundsCorner.z)
    ) {
      continue;
    }

    const screenX = ((projectedBoundsCorner.x + 1) * 0.5) * viewportWidth;
    const screenY = ((1 - projectedBoundsCorner.y) * 0.5) * viewportHeight;
    minScreenX = Math.min(minScreenX, screenX);
    maxScreenX = Math.max(maxScreenX, screenX);
    minScreenY = Math.min(minScreenY, screenY);
    maxScreenY = Math.max(maxScreenY, screenY);
    projectedCornerCount += 1;
  }

  if (projectedCornerCount === 0) {
    return null;
  }

  return {
    minX: minScreenX,
    maxX: maxScreenX,
    minY: minScreenY,
    maxY: maxScreenY,
  };
}

function measureProjectedBoundsMaxExtentPx(
  bounds: THREE.Box3,
  matrixWorld: THREE.Matrix4,
  camera: THREE.Camera,
  viewportWidth: number,
  viewportHeight: number,
): number | null {
  const rect = measureProjectedBoundsRectPx(bounds, matrixWorld, camera, viewportWidth, viewportHeight);
  if (!rect) {
    return null;
  }

  return Math.max(rect.maxX - rect.minX, rect.maxY - rect.minY);
}

function measurePointerDistanceToProjectedBoundsPx(
  bounds: THREE.Box3,
  matrixWorld: THREE.Matrix4,
  camera: THREE.Camera,
  viewportWidth: number,
  viewportHeight: number,
  pointerScreenX: number,
  pointerScreenY: number,
): number | null {
  const rect = measureProjectedBoundsRectPx(bounds, matrixWorld, camera, viewportWidth, viewportHeight);
  if (!rect) {
    return null;
  }

  const dx = pointerScreenX < rect.minX
    ? rect.minX - pointerScreenX
    : pointerScreenX > rect.maxX
      ? pointerScreenX - rect.maxX
      : 0;
  const dy = pointerScreenY < rect.minY
    ? rect.minY - pointerScreenY
    : pointerScreenY > rect.maxY
      ? pointerScreenY - rect.maxY
      : 0;

  return Math.hypot(dx, dy);
}

export function findNearestExpandedBoundsHit<TMeta>(
  ray: THREE.Ray,
  candidates: Iterable<HoverBoundsCandidate<TMeta>>,
  getLinkKey: (meta: TMeta) => string,
  options: HoverBoundsOptions = {},
): HoverMatch<TMeta> | null {
  const minPadding = options.minPadding ?? DEFAULT_MIN_PADDING;
  const paddingRatio = options.paddingRatio ?? DEFAULT_PADDING_RATIO;
  const minProjectedPaddingPx = options.minProjectedPaddingPx ?? DEFAULT_MIN_PROJECTED_PADDING_PX;
  const maxProjectedSizePx = options.maxProjectedSizePx ?? DEFAULT_MAX_PROJECTED_SIZE_PX;
  const maxPointerDistancePx = options.maxPointerDistancePx ?? DEFAULT_MAX_POINTER_DISTANCE_PX;
  const hasPointerScreenPosition = Number.isFinite(options.pointerScreenX) && Number.isFinite(options.pointerScreenY);

  let bestHit: HoverMatch<TMeta> | null = null;

  for (const candidate of candidates) {
    const geometry = candidate.mesh.geometry;
    if (!geometry) {
      continue;
    }

    if (!geometry.boundingBox) {
      geometry.computeBoundingBox();
    }
    if (!geometry.boundingBox) {
      continue;
    }

    const linkKey = getLinkKey(candidate.meta);
    if (!linkKey) {
      continue;
    }

    const localBounds = geometry.boundingBox;

    if (options.camera && options.viewportWidth && options.viewportHeight) {
      const projectedSizePx = measureProjectedBoundsMaxExtentPx(
        localBounds,
        candidate.mesh.matrixWorld,
        options.camera,
        options.viewportWidth,
        options.viewportHeight,
      );

      if (projectedSizePx !== null && projectedSizePx > maxProjectedSizePx) {
        continue;
      }

      if (hasPointerScreenPosition) {
        const pointerDistancePx = measurePointerDistanceToProjectedBoundsPx(
          localBounds,
          candidate.mesh.matrixWorld,
          options.camera,
          options.viewportWidth,
          options.viewportHeight,
          options.pointerScreenX as number,
          options.pointerScreenY as number,
        );

        if (pointerDistancePx !== null && pointerDistancePx > maxPointerDistancePx) {
          continue;
        }
      }
    }

    localBounds.getSize(pooledBoundsSize);
    candidate.mesh.matrixWorld.decompose(
      pooledWorldPosition,
      pooledWorldQuaternion,
      pooledWorldScale,
    );

    const scaleX = Math.abs(pooledWorldScale.x);
    const scaleY = Math.abs(pooledWorldScale.y);
    const scaleZ = Math.abs(pooledWorldScale.z);
    const meshMaxExtent = Math.max(
      pooledBoundsSize.x * scaleX,
      pooledBoundsSize.y * scaleY,
      pooledBoundsSize.z * scaleZ,
    );
    const projectedPadding = options.camera && options.viewportWidth && options.viewportHeight
      ? (() => {
          const projectedSizePx = measureProjectedBoundsMaxExtentPx(
            localBounds,
            candidate.mesh.matrixWorld,
            options.camera,
            options.viewportWidth,
            options.viewportHeight,
          );
          if (!projectedSizePx || projectedSizePx <= 0 || !Number.isFinite(projectedSizePx)) {
            return 0;
          }
          return (meshMaxExtent / projectedSizePx) * minProjectedPaddingPx;
        })()
      : 0;
    const padding = Math.max(meshMaxExtent * paddingRatio, projectedPadding, minPadding);

    pooledLocalPaddingVector.set(
      scaleX > Number.EPSILON ? padding / scaleX : padding,
      scaleY > Number.EPSILON ? padding / scaleY : padding,
      scaleZ > Number.EPSILON ? padding / scaleZ : padding,
    );
    pooledExpandedBounds.copy(localBounds).expandByVector(pooledLocalPaddingVector);

    pooledInverseMatrix.copy(candidate.mesh.matrixWorld).invert();
    pooledLocalRay.copy(ray).applyMatrix4(pooledInverseMatrix);
    const hitPoint = pooledLocalRay.intersectBox(pooledExpandedBounds, pooledLocalHitPoint);
    if (!hitPoint) {
      continue;
    }

    const distance = ray.origin.distanceTo(
      pooledWorldHitPoint.copy(hitPoint).applyMatrix4(candidate.mesh.matrixWorld),
    );
    if (!bestHit || distance < bestHit.distance) {
      bestHit = {
        meta: candidate.meta,
        distance,
        padding,
      };
    }
  }

  return bestHit;
}

export function choosePreferredHoverMatch<TMeta>(
  exactMatch: HoverMatch<TMeta> | null,
  boundsMatch: HoverMatch<TMeta> | null,
  getLinkKey: (meta: TMeta) => string,
): HoverMatch<TMeta> | null {
  if (!boundsMatch) {
    return exactMatch;
  }

  if (!exactMatch) {
    return boundsMatch;
  }

  const exactLinkKey = getLinkKey(exactMatch.meta);
  const boundsLinkKey = getLinkKey(boundsMatch.meta);
  if (exactLinkKey === boundsLinkKey) {
    return exactMatch;
  }

  // Expanded bounds are only a fallback for missed or tiny geometry. Once the
  // ray has a real mesh hit, that surface should always win over a neighboring
  // link's inflated proxy bounds.
  return exactMatch;
}

export function resolvePreferredHoverMatch<TMeta>({
  exactMatch,
  ray,
  candidates,
  getLinkKey,
  boundsOptions,
}: ResolvePreferredHoverMatchOptions<TMeta>): ResolvedHoverMatch<TMeta> | null {
  const boundsMatch = findNearestExpandedBoundsHit(
    ray,
    candidates,
    getLinkKey,
    boundsOptions,
  );
  const match = choosePreferredHoverMatch(exactMatch, boundsMatch, getLinkKey);
  if (!match) {
    return null;
  }

  return {
    match,
    source: match === exactMatch ? 'exact' : 'bounds',
  };
}
