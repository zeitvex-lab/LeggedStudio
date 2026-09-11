export function resolveRegressionRuntimeRobot<TRobot>({
  robot,
  jointPanelRobot,
  includePrimaryRobot = true,
}: {
  robot: TRobot | null | undefined;
  jointPanelRobot: TRobot | null | undefined;
  includePrimaryRobot?: boolean;
}): TRobot | null {
  return jointPanelRobot ?? (includePrimaryRobot ? (robot ?? null) : null);
}
