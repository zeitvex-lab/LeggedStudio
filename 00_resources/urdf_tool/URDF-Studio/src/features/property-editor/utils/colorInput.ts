import { parseThreeColorWithOpacity } from '@/core/utils/color.ts';

function clampOpacityToHex(opacity: number): string {
  const channel = Math.max(0, Math.min(255, Math.round(opacity * 255)));
  return channel.toString(16).padStart(2, '0');
}

function clampOpacityValue(opacity: number): number {
  if (!Number.isFinite(opacity)) {
    return 1;
  }

  return Math.min(1, Math.max(0, opacity));
}

export function getColorPickerHexValue(
  value?: string | null,
  fallback = '#ffffff',
): string {
  const parsed = parseThreeColorWithOpacity(value) || parseThreeColorWithOpacity(fallback);
  return parsed ? `#${parsed.color.getHexString()}` : '#ffffff';
}

export function mergeColorPickerHexValue(
  nextPickerValue: string,
  previousColor?: string | null,
): string {
  const nextHex = getColorPickerHexValue(nextPickerValue);
  const previousParsed = parseThreeColorWithOpacity(previousColor);

  if (previousParsed?.opacity == null) {
    return nextHex;
  }

  return `${nextHex}${clampOpacityToHex(previousParsed.opacity)}`;
}

export function getColorOpacityValue(
  value?: string | null,
  fallback = 1,
): number {
  const parsed = parseThreeColorWithOpacity(value);
  return parsed?.opacity == null ? clampOpacityValue(fallback) : clampOpacityValue(parsed.opacity);
}

export function mergeColorOpacityValue(
  previousColor: string | null | undefined,
  opacity: number,
  fallbackColor = '#ffffff',
): string {
  const baseHex = getColorPickerHexValue(previousColor, fallbackColor);
  const clampedOpacity = clampOpacityValue(opacity);
  return clampedOpacity >= 0.999 ? baseHex : `${baseHex}${clampOpacityToHex(clampedOpacity)}`;
}
