import type { ConversionResult, GeomData } from './conversionTypes';
import { toPositive } from './conversionMath';

export const DEFAULT_DIMENSIONS = { x: 0.1, y: 0.5, z: 0.1 };
export const DEFAULT_ORIGIN = {
  xyz: { x: 0, y: 0, z: 0 },
  rpy: { r: 0, p: 0, y: 0 },
};

export function normalizeOrigin(origin: GeomData['origin']): ConversionResult['origin'] {
  return {
    xyz: {
      x: origin?.xyz?.x ?? DEFAULT_ORIGIN.xyz.x,
      y: origin?.xyz?.y ?? DEFAULT_ORIGIN.xyz.y,
      z: origin?.xyz?.z ?? DEFAULT_ORIGIN.xyz.z,
    },
    rpy: {
      r: origin?.rpy?.r ?? DEFAULT_ORIGIN.rpy.r,
      p: origin?.rpy?.p ?? DEFAULT_ORIGIN.rpy.p,
      y: origin?.rpy?.y ?? DEFAULT_ORIGIN.rpy.y,
    },
  };
}

export function normalizeDimensions(dimensions: GeomData['dimensions']): {
  x: number;
  y: number;
  z: number;
} {
  return {
    x: toPositive(dimensions?.x, DEFAULT_DIMENSIONS.x),
    y: toPositive(dimensions?.y, DEFAULT_DIMENSIONS.y),
    z: toPositive(dimensions?.z, DEFAULT_DIMENSIONS.z),
  };
}
