import * as THREE from 'three';

import { GeometryType } from '@/types';
import { canonicalizeAxis, type Point3 } from '@/core/geometry/primitiveGeometry';
import type { ConversionResult, GeomData, ScalarInterval } from './conversionTypes';
import { normalizeDimensions, normalizeOrigin } from './conversionDefaults';
import {
  composePrimitiveLength,
  computePrimitiveVolume,
  computeSweepHalfExtent,
  getAxisVectorForPrimaryAxis,
  toPositive,
} from './conversionMath';
import {
  choosePreferredInterval,
  mergeIntervals,
  subtractBlockedInterval,
} from './collisionIntervals';
import { computeOverlapAllowance } from './clearanceMetrics';
import { offsetOriginByLocalVector, rotateLocalVectorByOrigin } from './originTransforms';

const _tempVec3A = new THREE.Vector3();
const _tempVec3B = new THREE.Vector3();
const _tempVec3C = new THREE.Vector3();

function computeBroadPhaseRadius(geometry: GeomData): number | null {
  const type = geometry.type ?? GeometryType.NONE;
  const dims = normalizeDimensions(geometry.dimensions);

  switch (type) {
    case GeometryType.SPHERE:
      return toPositive(dims.x, 0.05);
    case GeometryType.ELLIPSOID:
      return Math.max(toPositive(dims.x, 0.05), toPositive(dims.y, 0.05), toPositive(dims.z, 0.05));
    case GeometryType.BOX:
      return Math.hypot(dims.x, dims.y, dims.z) / 2;
    case GeometryType.CYLINDER:
      return Math.hypot(toPositive(dims.x, 0.05), toPositive(dims.y, 0.1) / 2);
    case GeometryType.CAPSULE:
      return Math.max(toPositive(dims.y, 0.1) / 2, toPositive(dims.x, 0.05));
    default:
      return null;
  }
}

function collectSiblingBroadPhaseSpheres(
  siblingGeometries: GeomData[] | undefined,
): { center: THREE.Vector3; radius: number }[] {
  if (!siblingGeometries?.length) {
    return [];
  }

  return siblingGeometries
    .map((geometry) => {
      const radius = computeBroadPhaseRadius(geometry);
      if (!radius || radius <= 1e-8) {
        return null;
      }

      const origin = normalizeOrigin(geometry.origin);
      return {
        center: new THREE.Vector3(origin.xyz.x, origin.xyz.y, origin.xyz.z),
        radius,
      };
    })
    .filter((sphere): sphere is { center: THREE.Vector3; radius: number } => sphere !== null);
}

function buildBlockedCenterIntervals(
  candidateCenter: THREE.Vector3,
  axisVector: THREE.Vector3,
  primitiveRadius: number,
  siblingSpheres: { center: THREE.Vector3; radius: number }[],
  clearance: number,
): ScalarInterval[] {
  const blockedIntervals: ScalarInterval[] = [];

  siblingSpheres.forEach((sibling) => {
    _tempVec3A.copy(sibling.center).sub(candidateCenter);
    const projection = _tempVec3A.dot(axisVector);
    _tempVec3B.copy(axisVector).multiplyScalar(projection);
    _tempVec3C.copy(_tempVec3A).sub(_tempVec3B);

    const radialDistance = _tempVec3C.length();
    const combinedRadius = primitiveRadius + sibling.radius + clearance;
    if (radialDistance >= combinedRadius) {
      return;
    }

    const axialPadding = Math.sqrt(
      Math.max(combinedRadius * combinedRadius - radialDistance * radialDistance, 0),
    );
    blockedIntervals.push({
      start: projection - axialPadding,
      end: projection + axialPadding,
    });
  });

  return mergeIntervals(blockedIntervals);
}

function findNearestSafeCenterShift(
  candidateCenter: THREE.Vector3,
  axisVector: THREE.Vector3,
  primitiveRadius: number,
  siblingSpheres: { center: THREE.Vector3; radius: number }[],
  clearance: number,
): number {
  const blockedIntervals = buildBlockedCenterIntervals(
    candidateCenter,
    axisVector,
    primitiveRadius,
    siblingSpheres,
    clearance,
  );

  const blockingInterval = blockedIntervals.find(
    (interval) => interval.start <= 0 + 1e-8 && interval.end >= 0 - 1e-8,
  );

  if (!blockingInterval) {
    return 0;
  }

  const leftMagnitude = Math.abs(blockingInterval.start);
  const rightMagnitude = Math.abs(blockingInterval.end);

  if (leftMagnitude < rightMagnitude - 1e-8) {
    return blockingInterval.start;
  }

  if (rightMagnitude < leftMagnitude - 1e-8) {
    return blockingInterval.end;
  }

  return blockingInterval.end;
}

function resolveAvailableSweepInterval(
  candidateCenter: THREE.Vector3,
  axisVector: THREE.Vector3,
  sweepHalfExtent: number,
  primitiveRadius: number,
  siblingSpheres: { center: THREE.Vector3; radius: number }[],
  clearance: number,
): { centerShift: number; sweepHalfExtent: number } | null {
  if (sweepHalfExtent <= 1e-8) {
    const hasOverlapAtCenter = siblingSpheres.some((sibling) => {
      _tempVec3A.copy(sibling.center).sub(candidateCenter);
      const projection = _tempVec3A.dot(axisVector);
      _tempVec3B.copy(axisVector).multiplyScalar(projection);
      _tempVec3C.copy(_tempVec3A).sub(_tempVec3B);
      const radialDistance = _tempVec3C.length();
      return (
        radialDistance + 1e-8 < primitiveRadius + sibling.radius + clearance &&
        Math.abs(projection) <= 1e-8
      );
    });

    return hasOverlapAtCenter
      ? null
      : {
          centerShift: 0,
          sweepHalfExtent: 0,
        };
  }

  let intervals: ScalarInterval[] = [{ start: -sweepHalfExtent, end: sweepHalfExtent }];

  siblingSpheres.forEach((sibling) => {
    _tempVec3A.copy(sibling.center).sub(candidateCenter);
    const projection = _tempVec3A.dot(axisVector);
    _tempVec3B.copy(axisVector).multiplyScalar(projection);
    _tempVec3C.copy(_tempVec3A).sub(_tempVec3B);

    const radialDistance = _tempVec3C.length();
    const combinedRadius = primitiveRadius + sibling.radius + clearance;
    if (radialDistance >= combinedRadius) {
      return;
    }

    const axialPadding = Math.sqrt(
      Math.max(combinedRadius * combinedRadius - radialDistance * radialDistance, 0),
    );
    intervals = subtractBlockedInterval(
      intervals,
      projection - axialPadding,
      projection + axialPadding,
    );
  });

  const preferredInterval = choosePreferredInterval(intervals);
  if (!preferredInterval) {
    return null;
  }

  return {
    centerShift: (preferredInterval.start + preferredInterval.end) / 2,
    sweepHalfExtent: Math.max((preferredInterval.end - preferredInterval.start) / 2, 0),
  };
}

function collectRadiusCandidates(
  primitiveRadius: number,
  candidateCenter: THREE.Vector3,
  axisVector: THREE.Vector3,
  siblingSpheres: { center: THREE.Vector3; radius: number }[],
  clearance: number,
  minRadius: number,
): number[] {
  const candidates = new Set<number>([primitiveRadius, minRadius]);

  siblingSpheres.forEach((sibling) => {
    _tempVec3A.copy(sibling.center).sub(candidateCenter);
    const projection = _tempVec3A.dot(axisVector);
    _tempVec3B.copy(axisVector).multiplyScalar(projection);
    _tempVec3C.copy(_tempVec3A).sub(_tempVec3B);

    const radialDistance = _tempVec3C.length();
    candidates.add(Math.max(radialDistance - sibling.radius - clearance, minRadius));
  });

  return Array.from(candidates)
    .filter((value) => Number.isFinite(value) && value >= minRadius)
    .sort((left, right) => right - left);
}

export function applySiblingCollisionClearance(
  primitiveRadius: number,
  primitiveLength: number,
  axisInLinkSpace: Point3,
  newType: GeometryType,
  siblingGeometries: GeomData[] | undefined,
  centerOrigin: ConversionResult['origin'],
  overlapAllowanceRatio?: number,
): { radius: number; length: number; centerShift: number } {
  if (
    (newType !== GeometryType.CYLINDER && newType !== GeometryType.CAPSULE) ||
    !siblingGeometries?.length
  ) {
    return {
      radius: primitiveRadius,
      length: primitiveLength,
      centerShift: 0,
    };
  }

  const axis = canonicalizeAxis(axisInLinkSpace);
  if (!axis) {
    return {
      radius: primitiveRadius,
      length: primitiveLength,
      centerShift: 0,
    };
  }

  const siblingSpheres = collectSiblingBroadPhaseSpheres(siblingGeometries);
  if (siblingSpheres.length === 0) {
    return {
      radius: primitiveRadius,
      length: primitiveLength,
      centerShift: 0,
    };
  }

  const candidateCenter = new THREE.Vector3(
    centerOrigin.xyz.x,
    centerOrigin.xyz.y,
    centerOrigin.xyz.z,
  );
  const axisVector = new THREE.Vector3(axis.x, axis.y, axis.z).normalize();
  const radius = toPositive(primitiveRadius, 0.05);
  const minSize = 1e-4;
  const baseClearance = Math.min(Math.max(radius * 0.05, 0.002), 0.01);
  const clearance = baseClearance - computeOverlapAllowance(radius, overlapAllowanceRatio);
  const minRadius = Math.min(Math.max(radius * 0.15, minSize), radius);
  const radiusCandidates = collectRadiusCandidates(
    radius,
    candidateCenter,
    axisVector,
    siblingSpheres,
    clearance,
    minRadius,
  );

  let bestCandidate: {
    radius: number;
    sweepHalfExtent: number;
    centerShift: number;
    volume: number;
  } | null = null;

  for (const radiusCandidate of radiusCandidates) {
    const sweepHalfExtent = computeSweepHalfExtent(radiusCandidate, primitiveLength, newType);
    const safeInterval = resolveAvailableSweepInterval(
      candidateCenter,
      axisVector,
      sweepHalfExtent,
      radiusCandidate,
      siblingSpheres,
      clearance,
    );

    if (!safeInterval) {
      continue;
    }

    const length = composePrimitiveLength(safeInterval.sweepHalfExtent, radiusCandidate, newType);
    const volume = computePrimitiveVolume(newType, radiusCandidate, length);
    if (!Number.isFinite(volume) || volume <= 0) {
      continue;
    }

    const nextCandidate = {
      radius: radiusCandidate,
      sweepHalfExtent: safeInterval.sweepHalfExtent,
      centerShift: safeInterval.centerShift,
      volume,
    };

    if (!bestCandidate) {
      bestCandidate = nextCandidate;
      continue;
    }

    const volumeTolerance = Math.max(bestCandidate.volume * 0.01, 1e-8);
    if (nextCandidate.volume > bestCandidate.volume + volumeTolerance) {
      bestCandidate = nextCandidate;
      continue;
    }

    if (Math.abs(nextCandidate.volume - bestCandidate.volume) <= volumeTolerance) {
      if (nextCandidate.sweepHalfExtent > bestCandidate.sweepHalfExtent + 1e-8) {
        bestCandidate = nextCandidate;
        continue;
      }

      if (
        Math.abs(nextCandidate.sweepHalfExtent - bestCandidate.sweepHalfExtent) <= 1e-8 &&
        Math.abs(nextCandidate.centerShift) < Math.abs(bestCandidate.centerShift) - 1e-8
      ) {
        bestCandidate = nextCandidate;
      }
    }
  }

  if (bestCandidate) {
    return {
      radius: bestCandidate.radius,
      length: composePrimitiveLength(bestCandidate.sweepHalfExtent, bestCandidate.radius, newType),
      centerShift: bestCandidate.centerShift,
    };
  }

  let fallbackCandidate: {
    radius: number;
    length: number;
    centerShift: number;
    volume: number;
  } | null = null;

  for (const radiusCandidate of radiusCandidates) {
    const centerShift = findNearestSafeCenterShift(
      candidateCenter,
      axisVector,
      radiusCandidate,
      siblingSpheres,
      clearance,
    );
    const length = composePrimitiveLength(
      newType === GeometryType.CAPSULE ? 0 : minSize / 2,
      radiusCandidate,
      newType,
    );
    const volume = computePrimitiveVolume(newType, radiusCandidate, length);
    if (!Number.isFinite(volume) || volume <= 0) {
      continue;
    }

    const nextCandidate = {
      radius: radiusCandidate,
      length,
      centerShift,
      volume,
    };

    if (!fallbackCandidate) {
      fallbackCandidate = nextCandidate;
      continue;
    }

    const shiftDelta =
      Math.abs(nextCandidate.centerShift) - Math.abs(fallbackCandidate.centerShift);
    if (shiftDelta < -1e-8) {
      fallbackCandidate = nextCandidate;
      continue;
    }

    if (Math.abs(shiftDelta) <= 1e-8) {
      const volumeTolerance = Math.max(fallbackCandidate.volume * 0.01, 1e-8);
      if (nextCandidate.volume > fallbackCandidate.volume + volumeTolerance) {
        fallbackCandidate = nextCandidate;
      }
    }
  }

  if (fallbackCandidate) {
    return {
      radius: fallbackCandidate.radius,
      length: fallbackCandidate.length,
      centerShift: fallbackCandidate.centerShift,
    };
  }

  return {
    radius,
    length: composePrimitiveLength(
      newType === GeometryType.CAPSULE ? 0 : minSize / 2,
      radius,
      newType,
    ),
    centerShift: 0,
  };
}

export function applySiblingBoxClearance(
  boxDimensions: { x: number; y: number; z: number },
  origin: ConversionResult['origin'],
  siblingGeometries: GeomData[] | undefined,
): ConversionResult['origin'] {
  if (!siblingGeometries?.length) {
    return origin;
  }

  const siblingSpheres = collectSiblingBroadPhaseSpheres(siblingGeometries);
  if (siblingSpheres.length === 0) {
    return origin;
  }

  const boxRadius = computeBroadPhaseRadius({
    type: GeometryType.BOX,
    dimensions: boxDimensions,
    origin,
  });
  if (!boxRadius || boxRadius <= 1e-8) {
    return origin;
  }

  const center = new THREE.Vector3(origin.xyz.x, origin.xyz.y, origin.xyz.z);
  const clearance = Math.min(Math.max(boxRadius * 0.05, 0.002), 0.01);
  const axisPriority = [
    { axis: 'x' as const, size: boxDimensions.x },
    { axis: 'y' as const, size: boxDimensions.y },
    { axis: 'z' as const, size: boxDimensions.z },
  ].sort((left, right) => right.size - left.size);

  let bestShift: { localAxis: Point3; centerShift: number } | null = null;

  for (const { axis } of axisPriority) {
    const localAxis = getAxisVectorForPrimaryAxis(axis);
    const axisInLinkSpace = rotateLocalVectorByOrigin(origin, localAxis);
    const centerShift = findNearestSafeCenterShift(
      center,
      _tempVec3A.set(axisInLinkSpace.x, axisInLinkSpace.y, axisInLinkSpace.z).normalize(),
      boxRadius,
      siblingSpheres,
      clearance,
    );

    if (!bestShift) {
      bestShift = { localAxis, centerShift };
      continue;
    }

    const nextShiftMagnitude = Math.abs(centerShift);
    const bestShiftMagnitude = Math.abs(bestShift.centerShift);
    if (nextShiftMagnitude < bestShiftMagnitude - 1e-8) {
      bestShift = { localAxis, centerShift };
      continue;
    }

    if (
      Math.abs(nextShiftMagnitude - bestShiftMagnitude) <= 1e-8 &&
      axis === axisPriority[0].axis
    ) {
      bestShift = { localAxis, centerShift };
    }
  }

  if (!bestShift || Math.abs(bestShift.centerShift) <= 1e-8) {
    return origin;
  }

  return offsetOriginByLocalVector(origin, {
    x: bestShift.localAxis.x * bestShift.centerShift,
    y: bestShift.localAxis.y * bestShift.centerShift,
    z: bestShift.localAxis.z * bestShift.centerShift,
  });
}
