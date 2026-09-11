export function computeOverlapAllowance(
  primitiveRadius: number,
  overlapAllowanceRatio: number | undefined,
): number {
  if (
    !Number.isFinite(overlapAllowanceRatio) ||
    !overlapAllowanceRatio ||
    overlapAllowanceRatio <= 0
  ) {
    return 0;
  }

  const safeRatio = Math.min(Math.max(overlapAllowanceRatio, 0), 0.35);
  return Math.min(Math.max(primitiveRadius * safeRatio, 0), primitiveRadius * 0.35);
}
