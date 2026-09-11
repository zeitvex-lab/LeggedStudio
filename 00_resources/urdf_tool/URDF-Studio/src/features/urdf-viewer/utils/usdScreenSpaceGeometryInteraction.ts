import type { ViewerInteractiveLayer } from '../types';
import type { UsdInteractiveGeometryRole } from './usdInteractionPicking';

export interface ProjectedUsdGeometryTarget<TMeta> {
  meta: TMeta;
  layer: UsdInteractiveGeometryRole;
  clientX: number;
  clientY: number;
  projectedWidth: number;
  projectedHeight: number;
  projectedArea: number;
  averageDepth: number;
}

const MIN_GEOMETRY_HIT_PADDING_PX = 6;
const MAX_GEOMETRY_HIT_PADDING_PX = 18;
const GEOMETRY_HIT_PADDING_RATIO = 0.08;
const MIN_NORMALIZATION_EXTENT_PX = 8;

function getLayerRank(
  layer: UsdInteractiveGeometryRole,
  interactionLayerPriority: readonly ViewerInteractiveLayer[] | undefined,
): number {
  if (!interactionLayerPriority || interactionLayerPriority.length === 0) {
    return layer === 'visual' ? 0 : 1;
  }

  const index = interactionLayerPriority.indexOf(layer);
  return index >= 0 ? index : interactionLayerPriority.length + (layer === 'visual' ? 0 : 1);
}

function resolvePadding(projectedWidth: number, projectedHeight: number): number {
  const maxExtent = Math.max(projectedWidth, projectedHeight);
  const scaled = maxExtent * GEOMETRY_HIT_PADDING_RATIO;
  return Math.min(MAX_GEOMETRY_HIT_PADDING_PX, Math.max(MIN_GEOMETRY_HIT_PADDING_PX, scaled));
}

function scoreProjectedTarget<TMeta>(
  target: ProjectedUsdGeometryTarget<TMeta>,
  pointerClientX: number,
  pointerClientY: number,
  interactionLayerPriority: readonly ViewerInteractiveLayer[] | undefined,
) {
  const halfWidth = Math.max(0, target.projectedWidth / 2);
  const halfHeight = Math.max(0, target.projectedHeight / 2);
  const padding = resolvePadding(target.projectedWidth, target.projectedHeight);
  const centerDx = Math.abs(pointerClientX - target.clientX);
  const centerDy = Math.abs(pointerClientY - target.clientY);

  if (centerDx > halfWidth + padding || centerDy > halfHeight + padding) {
    return null;
  }

  const normalizedCenterDistance = Math.hypot(
    centerDx / Math.max(halfWidth, MIN_NORMALIZATION_EXTENT_PX),
    centerDy / Math.max(halfHeight, MIN_NORMALIZATION_EXTENT_PX),
  );

  return {
    layerRank: getLayerRank(target.layer, interactionLayerPriority),
    normalizedCenterDistance,
    projectedArea: target.projectedArea,
    averageDepth: target.averageDepth,
  };
}

export function resolveScreenSpaceUsdGeometryHit<TMeta>(options: {
  pointerClientX: number;
  pointerClientY: number;
  projectedGeometry: readonly ProjectedUsdGeometryTarget<TMeta>[];
  interactionLayerPriority?: readonly ViewerInteractiveLayer[];
}): ProjectedUsdGeometryTarget<TMeta> | null {
  const { pointerClientX, pointerClientY, projectedGeometry, interactionLayerPriority } = options;

  let best:
    | {
        target: ProjectedUsdGeometryTarget<TMeta>;
        score: NonNullable<ReturnType<typeof scoreProjectedTarget<TMeta>>>;
      }
    | null = null;

  for (const target of projectedGeometry) {
    if (
      !Number.isFinite(target.clientX) ||
      !Number.isFinite(target.clientY) ||
      !Number.isFinite(target.projectedWidth) ||
      !Number.isFinite(target.projectedHeight) ||
      target.projectedWidth <= 0 ||
      target.projectedHeight <= 0
    ) {
      continue;
    }

    const score = scoreProjectedTarget(
      target,
      pointerClientX,
      pointerClientY,
      interactionLayerPriority,
    );
    if (!score) {
      continue;
    }

    if (!best) {
      best = { target, score };
      continue;
    }

    if (score.layerRank !== best.score.layerRank) {
      if (score.layerRank < best.score.layerRank) {
        best = { target, score };
      }
      continue;
    }

    if (score.normalizedCenterDistance !== best.score.normalizedCenterDistance) {
      if (score.normalizedCenterDistance < best.score.normalizedCenterDistance) {
        best = { target, score };
      }
      continue;
    }

    if (score.projectedArea !== best.score.projectedArea) {
      if (score.projectedArea < best.score.projectedArea) {
        best = { target, score };
      }
      continue;
    }

    if (score.averageDepth < best.score.averageDepth) {
      best = { target, score };
    }
  }

  return best?.target ?? null;
}
