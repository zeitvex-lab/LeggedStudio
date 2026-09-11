import type { UrdfVisualMaterial } from '@/types';

import { getColorOpacityValue, mergeColorOpacityValue } from './colorInput';

export function clampMaterialOpacity(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }

  return Math.min(1, Math.max(0, value));
}

export function normalizeMaterialColor(value?: string | null): string | undefined {
  const normalized = value?.trim().toLowerCase();
  return normalized || undefined;
}

export function getUniqueAuthoredMaterialColors(
  materials: readonly UrdfVisualMaterial[] | null | undefined,
): string[] {
  const uniqueColors: string[] = [];
  const seenColors = new Set<string>();

  for (const material of materials ?? []) {
    const rawColor = material.color?.trim();
    const normalizedColor = normalizeMaterialColor(rawColor);

    if (!rawColor || !normalizedColor || seenColors.has(normalizedColor)) {
      continue;
    }

    seenColors.add(normalizedColor);
    uniqueColors.push(rawColor);
  }

  return uniqueColors;
}

export function getAuthoredMaterialOpacity(
  material: UrdfVisualMaterial | null | undefined,
  fallbackColor?: string | null,
): number {
  if (Number.isFinite(material?.opacity)) {
    return clampMaterialOpacity(Number(material?.opacity));
  }

  if (
    Array.isArray(material?.colorRgba) &&
    material.colorRgba.length === 4 &&
    Number.isFinite(material.colorRgba[3])
  ) {
    return clampMaterialOpacity(Number(material.colorRgba[3]));
  }

  return getColorOpacityValue(material?.color, getColorOpacityValue(fallbackColor, 1));
}

export function withAuthoredMaterialOpacity(
  material: UrdfVisualMaterial,
  opacity: number,
): UrdfVisualMaterial {
  const nextOpacity = clampMaterialOpacity(opacity);
  return {
    ...material,
    ...(material.color ? { color: mergeColorOpacityValue(material.color, nextOpacity) } : {}),
    ...(material.colorRgba
      ? {
          colorRgba: [
            material.colorRgba[0],
            material.colorRgba[1],
            material.colorRgba[2],
            nextOpacity,
          ] as [number, number, number, number],
        }
      : {}),
    opacity: nextOpacity,
  };
}
