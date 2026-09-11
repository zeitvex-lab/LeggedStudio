import { GeometryType } from '@/types';
import {
  computeCapsuleVolume,
  computeCylinderVolume,
  type Point3,
} from '@/core/geometry/primitiveGeometry';
import type { MeshPrimaryAxis } from './conversionTypes';

export function toPositive(value: number | undefined, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return fallback;
  }
  return value;
}

export function getAxisVectorForPrimaryAxis(primaryAxis: MeshPrimaryAxis): Point3 {
  if (primaryAxis === 'x') return { x: 1, y: 0, z: 0 };
  if (primaryAxis === 'y') return { x: 0, y: 1, z: 0 };
  return { x: 0, y: 0, z: 1 };
}

export function computeSweepHalfExtent(
  primitiveRadius: number,
  primitiveLength: number,
  newType: GeometryType,
): number {
  if (newType === GeometryType.CAPSULE) {
    return Math.max(toPositive(primitiveLength, 0.1) / 2 - toPositive(primitiveRadius, 0.05), 0);
  }

  return toPositive(primitiveLength, 0.1) / 2;
}

export function composePrimitiveLength(
  sweepHalfExtent: number,
  primitiveRadius: number,
  newType: GeometryType,
): number {
  if (newType === GeometryType.CAPSULE) {
    return Math.max(sweepHalfExtent, 0) * 2 + toPositive(primitiveRadius, 0.05) * 2;
  }

  return Math.max(sweepHalfExtent, 0) * 2;
}

export function getPrimaryAxis(bounds: { x: number; y: number; z: number }): MeshPrimaryAxis {
  if (bounds.x >= bounds.y && bounds.x >= bounds.z) return 'x';
  if (bounds.y >= bounds.x && bounds.y >= bounds.z) return 'y';
  return 'z';
}

export function getCrossSectionDimensions(
  bounds: { x: number; y: number; z: number },
  primaryAxis: MeshPrimaryAxis,
): { length: number; crossA: number; crossB: number } {
  if (primaryAxis === 'x') {
    return { length: bounds.x, crossA: bounds.y, crossB: bounds.z };
  }
  if (primaryAxis === 'y') {
    return { length: bounds.y, crossA: bounds.x, crossB: bounds.z };
  }
  return { length: bounds.z, crossA: bounds.x, crossB: bounds.y };
}

export function computeApproximateCrossSectionRadius(crossA: number, crossB: number): number {
  if (!Number.isFinite(crossA) || !Number.isFinite(crossB) || crossA <= 0 || crossB <= 0) {
    return 0;
  }

  return Math.sqrt(crossA * crossB) / 2;
}

export function computeBoxVolume(bounds: { x: number; y: number; z: number }): number {
  return Math.max(bounds.x, 1e-8) * Math.max(bounds.y, 1e-8) * Math.max(bounds.z, 1e-8);
}

export function computeEquivalentSphereRadius(targetVolume: number): number {
  return Math.cbrt((3 * Math.max(targetVolume, 1e-8)) / (4 * Math.PI));
}

export function computeEquivalentCylinderRadius(length: number, targetVolume: number): number {
  if (!Number.isFinite(length) || length <= 1e-8) {
    return 0;
  }
  return Math.sqrt(Math.max(targetVolume, 1e-8) / (Math.PI * length));
}

export function computePrimitiveVolume(type: GeometryType, radius: number, length: number): number {
  if (type === GeometryType.CYLINDER) {
    return computeCylinderVolume(radius, length);
  }
  if (type === GeometryType.CAPSULE) {
    return computeCapsuleVolume(length, radius);
  }
  return Number.POSITIVE_INFINITY;
}

export function computeEquivalentCapsuleRadius(totalLength: number, targetVolume: number): number {
  if (!Number.isFinite(totalLength) || totalLength <= 1e-8) {
    return 0;
  }

  const safeVolume = Math.max(targetVolume, 1e-8);
  const maxRadius = totalLength / 2;
  const maxAchievableVolume = computeCapsuleVolume(totalLength, maxRadius);

  if (safeVolume >= maxAchievableVolume) {
    return maxRadius;
  }

  let low = 0;
  let high = maxRadius;

  for (let i = 0; i < 24; i += 1) {
    const mid = (low + high) / 2;
    if (computeCapsuleVolume(totalLength, mid) < safeVolume) {
      low = mid;
    } else {
      high = mid;
    }
  }

  return (low + high) / 2;
}
