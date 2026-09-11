const USD_GROUND_ALIGNMENT_SETTLE_DELAYS_MS = [
  0,
  80,
  200,
  400,
  800,
  1600,
  3000,
] as const;

export function resolveUsdGroundAlignmentSettleDelaysMs(
  stageSourcePath: string | null | undefined,
): readonly number[] {
  void stageSourcePath;
  return USD_GROUND_ALIGNMENT_SETTLE_DELAYS_MS;
}
