export function resolveUnifiedViewerUsageGuideVisibility(
  preference: boolean,
  override?: boolean,
): boolean {
  return override ?? preference;
}
