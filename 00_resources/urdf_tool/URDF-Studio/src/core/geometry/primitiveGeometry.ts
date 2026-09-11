export interface Point3 {
  x: number;
  y: number;
  z: number;
}

function withoutNegativeZero(value: number): number {
  return Object.is(value, -0) ? 0 : value;
}

export function canonicalizeAxis(axis: Point3): Point3 | null {
  const length = Math.hypot(axis.x, axis.y, axis.z);
  if (!Number.isFinite(length) || length <= 1e-8) return null;

  let normalized = {
    x: axis.x / length,
    y: axis.y / length,
    z: axis.z / length,
  };

  if (
    normalized.x < -1e-8 ||
    (Math.abs(normalized.x) <= 1e-8 && normalized.y < -1e-8) ||
    (Math.abs(normalized.x) <= 1e-8 && Math.abs(normalized.y) <= 1e-8 && normalized.z < 0)
  ) {
    normalized = {
      x: -normalized.x,
      y: -normalized.y,
      z: -normalized.z,
    };
  }

  return {
    x: withoutNegativeZero(normalized.x),
    y: withoutNegativeZero(normalized.y),
    z: withoutNegativeZero(normalized.z),
  };
}

export function computeAxisAlignmentScore(axis: Point3, preferredAxis: Point3): number {
  const normalizedAxis = canonicalizeAxis(axis);
  const normalizedPreferredAxis = canonicalizeAxis(preferredAxis);
  if (!normalizedAxis || !normalizedPreferredAxis) {
    return Number.NEGATIVE_INFINITY;
  }

  return Math.abs(
    normalizedAxis.x * normalizedPreferredAxis.x +
      normalizedAxis.y * normalizedPreferredAxis.y +
      normalizedAxis.z * normalizedPreferredAxis.z,
  );
}

export function computeCylinderVolume(radius: number, length: number): number {
  return Math.PI * radius * radius * Math.max(length, 0);
}

export function computeCapsuleVolume(totalLength: number, radius: number): number {
  if (totalLength <= 0 || radius <= 0) return 0;
  const clampedRadius = Math.min(radius, totalLength / 2);
  return (
    Math.PI * clampedRadius * clampedRadius * totalLength -
    (2 / 3) * Math.PI * clampedRadius * clampedRadius * clampedRadius
  );
}
