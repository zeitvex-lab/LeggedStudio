import * as THREE from 'three';

import { GeometryType } from '@/types';
import { canonicalizeAxis, type Point3 } from '@/core/geometry/primitiveGeometry';
import type { MeshClearanceObstacle } from './meshAnalysis';
import type { ConversionResult, MeshPrimaryAxis, ScalarInterval } from './conversionTypes';
import {
  composePrimitiveLength,
  computePrimitiveVolume,
  computeSweepHalfExtent,
  getAxisVectorForPrimaryAxis,
  getPrimaryAxis,
  toPositive,
} from './conversionMath';
import {
  findNearestSafeCenterShiftFromBlockedIntervals,
  mergeIntervals,
  resolveAvailableSweepIntervalFromBlockedIntervals,
} from './collisionIntervals';
import { computeOverlapAllowance } from './clearanceMetrics';
import { offsetOriginByLocalVector } from './originTransforms';

const _tempVec3A = new THREE.Vector3();
const _tempVec3B = new THREE.Vector3();
const _tempVec3C = new THREE.Vector3();

function collectMeshObstaclePoints(
  meshClearanceObstacles: MeshClearanceObstacle[] | undefined,
): Point3[] {
  if (!meshClearanceObstacles?.length) {
    return [];
  }

  const points: Point3[] = [];
  meshClearanceObstacles.forEach((obstacle) => {
    obstacle.points.forEach((point) => {
      points.push({ x: point.x, y: point.y, z: point.z });
    });
  });

  return points;
}

function buildMeshPointBlockedIntervals(
  candidateCenter: THREE.Vector3,
  axisVector: THREE.Vector3,
  sweepHalfExtent: number,
  primitiveRadius: number,
  meshObstaclePoints: Point3[],
  clearance: number,
  newType: GeometryType,
): ScalarInterval[] {
  const blockedIntervals: ScalarInterval[] = [];
  const radialLimit = primitiveRadius + clearance;

  meshObstaclePoints.forEach((point) => {
    _tempVec3A.set(point.x, point.y, point.z).sub(candidateCenter);
    const projection = _tempVec3A.dot(axisVector);
    _tempVec3B.copy(axisVector).multiplyScalar(projection);
    _tempVec3C.copy(_tempVec3A).sub(_tempVec3B);

    const radialDistance = _tempVec3C.length();
    if (radialDistance >= radialLimit) {
      return;
    }

    const axialPadding =
      newType === GeometryType.CAPSULE
        ? Math.sqrt(Math.max(radialLimit * radialLimit - radialDistance * radialDistance, 0))
        : 0;

    blockedIntervals.push({
      start: projection - sweepHalfExtent - axialPadding,
      end: projection + sweepHalfExtent + axialPadding,
    });
  });

  return mergeIntervals(blockedIntervals);
}

function collectRadiusCandidatesFromMeshPoints(
  primitiveRadius: number,
  candidateCenter: THREE.Vector3,
  axisVector: THREE.Vector3,
  meshObstaclePoints: Point3[],
  clearance: number,
  minRadius: number,
): number[] {
  const candidates = new Set<number>([primitiveRadius, minRadius]);

  meshObstaclePoints.forEach((point) => {
    _tempVec3A.set(point.x, point.y, point.z).sub(candidateCenter);
    const projection = _tempVec3A.dot(axisVector);
    _tempVec3B.copy(axisVector).multiplyScalar(projection);
    _tempVec3C.copy(_tempVec3A).sub(_tempVec3B);
    const radialDistance = _tempVec3C.length();
    candidates.add(Math.max(radialDistance - clearance, minRadius));
  });

  return Array.from(candidates)
    .filter((value) => Number.isFinite(value) && value >= minRadius)
    .sort((left, right) => right - left);
}

export function applyMeshPointCollisionClearance(
  primitiveRadius: number,
  primitiveLength: number,
  axisInLinkSpace: Point3,
  newType: GeometryType,
  meshClearanceObstacles: MeshClearanceObstacle[] | undefined,
  centerOrigin: ConversionResult['origin'],
  overlapAllowanceRatio?: number,
): { radius: number; length: number; centerShift: number } {
  if (
    (newType !== GeometryType.CYLINDER && newType !== GeometryType.CAPSULE) ||
    !meshClearanceObstacles?.length
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

  const meshObstaclePoints = collectMeshObstaclePoints(meshClearanceObstacles);
  if (meshObstaclePoints.length === 0) {
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
  const radiusCandidates = collectRadiusCandidatesFromMeshPoints(
    radius,
    candidateCenter,
    axisVector,
    meshObstaclePoints,
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
    const blockedIntervals = buildMeshPointBlockedIntervals(
      candidateCenter,
      axisVector,
      sweepHalfExtent,
      radiusCandidate,
      meshObstaclePoints,
      clearance,
      newType,
    );
    const safeInterval = resolveAvailableSweepIntervalFromBlockedIntervals(
      sweepHalfExtent,
      blockedIntervals,
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
    const fallbackHalfExtent = computeSweepHalfExtent(
      radiusCandidate,
      newType === GeometryType.CAPSULE ? radiusCandidate * 2 : minSize,
      newType,
    );
    const blockedIntervals = buildMeshPointBlockedIntervals(
      candidateCenter,
      axisVector,
      fallbackHalfExtent,
      radiusCandidate,
      meshObstaclePoints,
      clearance,
      newType,
    );
    const centerShift = findNearestSafeCenterShiftFromBlockedIntervals(blockedIntervals);
    const length = composePrimitiveLength(fallbackHalfExtent, radiusCandidate, newType);
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

function buildBoxPointBlockedIntervals(
  points: Point3[],
  center: THREE.Vector3,
  inverseRotation: THREE.Quaternion,
  majorAxis: MeshPrimaryAxis,
  halfMajor: number,
  halfCrossA: number,
  halfCrossB: number,
  clearance: number,
): ScalarInterval[] {
  const blockedIntervals: ScalarInterval[] = [];

  points.forEach((point) => {
    _tempVec3A.set(point.x, point.y, point.z).sub(center).applyQuaternion(inverseRotation);
    const majorCoord =
      majorAxis === 'x' ? _tempVec3A.x : majorAxis === 'y' ? _tempVec3A.y : _tempVec3A.z;
    const crossA =
      majorAxis === 'x' ? _tempVec3A.y : majorAxis === 'y' ? _tempVec3A.x : _tempVec3A.x;
    const crossB =
      majorAxis === 'x' ? _tempVec3A.z : majorAxis === 'y' ? _tempVec3A.z : _tempVec3A.y;

    if (Math.abs(crossA) >= halfCrossA + clearance || Math.abs(crossB) >= halfCrossB + clearance) {
      return;
    }

    blockedIntervals.push({
      start: majorCoord - halfMajor - clearance,
      end: majorCoord + halfMajor + clearance,
    });
  });

  return mergeIntervals(blockedIntervals);
}

export function applyMeshPointBoxClearance(
  boxDimensions: { x: number; y: number; z: number },
  origin: ConversionResult['origin'],
  meshClearanceObstacles: MeshClearanceObstacle[] | undefined,
): { dimensions: { x: number; y: number; z: number }; origin: ConversionResult['origin'] } {
  if (!meshClearanceObstacles?.length) {
    return {
      dimensions: boxDimensions,
      origin,
    };
  }

  const points = collectMeshObstaclePoints(meshClearanceObstacles);
  if (points.length === 0) {
    return {
      dimensions: boxDimensions,
      origin,
    };
  }

  const majorAxis = getPrimaryAxis(boxDimensions);
  const localAxis = getAxisVectorForPrimaryAxis(majorAxis);
  const halfMajor = Math.max(
    (majorAxis === 'x' ? boxDimensions.x : majorAxis === 'y' ? boxDimensions.y : boxDimensions.z) /
      2,
    1e-4,
  );
  const halfCrossA =
    majorAxis === 'x'
      ? boxDimensions.y / 2
      : majorAxis === 'y'
        ? boxDimensions.x / 2
        : boxDimensions.x / 2;
  const halfCrossB =
    majorAxis === 'x'
      ? boxDimensions.z / 2
      : majorAxis === 'y'
        ? boxDimensions.z / 2
        : boxDimensions.y / 2;
  const boxRadius = Math.hypot(boxDimensions.x, boxDimensions.y, boxDimensions.z) / 2;
  const clearance = Math.min(Math.max(boxRadius * 0.05, 0.002), 0.01);
  const center = new THREE.Vector3(origin.xyz.x, origin.xyz.y, origin.xyz.z);
  const inverseRotation = new THREE.Quaternion()
    .setFromEuler(new THREE.Euler(origin.rpy.r, origin.rpy.p, origin.rpy.y, 'ZYX'))
    .invert();
  const blockedIntervals = buildBoxPointBlockedIntervals(
    points,
    center,
    inverseRotation,
    majorAxis,
    halfMajor,
    halfCrossA,
    halfCrossB,
    clearance,
  );
  const safeInterval = resolveAvailableSweepIntervalFromBlockedIntervals(
    halfMajor,
    blockedIntervals,
  );

  if (safeInterval) {
    const nextOrigin =
      Math.abs(safeInterval.centerShift) > 1e-8
        ? offsetOriginByLocalVector(origin, {
            x: localAxis.x * safeInterval.centerShift,
            y: localAxis.y * safeInterval.centerShift,
            z: localAxis.z * safeInterval.centerShift,
          })
        : origin;
    const nextDimensions = { ...boxDimensions };
    const nextMajorSize = Math.max(safeInterval.sweepHalfExtent * 2, 1e-4);

    if (majorAxis === 'x') {
      nextDimensions.x = nextMajorSize;
    } else if (majorAxis === 'y') {
      nextDimensions.y = nextMajorSize;
    } else {
      nextDimensions.z = nextMajorSize;
    }

    return {
      dimensions: nextDimensions,
      origin: nextOrigin,
    };
  }

  const fallbackHalfExtent = 5e-5;
  const fallbackBlockedIntervals = buildBoxPointBlockedIntervals(
    points,
    center,
    inverseRotation,
    majorAxis,
    fallbackHalfExtent,
    halfCrossA,
    halfCrossB,
    clearance,
  );
  const fallbackShift = findNearestSafeCenterShiftFromBlockedIntervals(fallbackBlockedIntervals);
  const fallbackOrigin =
    Math.abs(fallbackShift) > 1e-8
      ? offsetOriginByLocalVector(origin, {
          x: localAxis.x * fallbackShift,
          y: localAxis.y * fallbackShift,
          z: localAxis.z * fallbackShift,
        })
      : origin;
  const fallbackDimensions = { ...boxDimensions };

  if (majorAxis === 'x') {
    fallbackDimensions.x = 1e-4;
  } else if (majorAxis === 'y') {
    fallbackDimensions.y = 1e-4;
  } else {
    fallbackDimensions.z = 1e-4;
  }

  return {
    dimensions: fallbackDimensions,
    origin: fallbackOrigin,
  };
}
