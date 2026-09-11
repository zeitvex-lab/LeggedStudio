import type { Vector3 } from '@/types';

const DEFAULT_BOX_DIMENSION = 0.1;

function sanitizeDimension(value: number | undefined): number {
  return Number.isFinite(value) && (value as number) > 0
    ? (value as number)
    : DEFAULT_BOX_DIMENSION;
}

export function getCollisionBoxDisplayCylinderTransform(dimensions: Vector3): {
  scale: [number, number, number];
  rotation: [number, number, number];
} {
  const x = sanitizeDimension(dimensions.x);
  const y = sanitizeDimension(dimensions.y);
  const z = sanitizeDimension(dimensions.z);

  // Preserve the authored box semantics in data, but render collision boxes as
  // cylinders aligned to the box's longest local axis.
  if (z >= x && z >= y) {
    return {
      scale: [x / 2, z, y / 2],
      rotation: [Math.PI / 2, 0, 0],
    };
  }

  if (y >= x) {
    return {
      scale: [x / 2, y, z / 2],
      rotation: [0, 0, 0],
    };
  }

  return {
    scale: [y / 2, x, z / 2],
    rotation: [0, 0, Math.PI / 2],
  };
}
