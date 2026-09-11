export function clampSliderValue(nextValue: number, min: number, max: number): number {
  if (!Number.isFinite(nextValue)) {
    return min;
  }

  return Math.min(Math.max(nextValue, min), max);
}

export function snapSliderValue(
  nextValue: number,
  min: number,
  max: number,
  currentStep: number,
): number {
  const clampedValue = clampSliderValue(nextValue, min, max);

  if (!Number.isFinite(currentStep) || currentStep <= 0) {
    return clampedValue;
  }

  const steppedValue = min + Math.round((clampedValue - min) / currentStep) * currentStep;
  const stepDecimals = `${currentStep}`.split('.')[1]?.length ?? 0;
  const precision = Math.min(stepDecimals + 2, 10);

  return clampSliderValue(Number(steppedValue.toFixed(precision)), min, max);
}
