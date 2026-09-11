export type CurrentUsdExportMode = 'bundle' | 'unavailable';

export interface ResolveCurrentUsdExportModeOptions {
  isHydrating: boolean;
  hasPreparedExportCache: boolean;
  hasSceneSnapshot: boolean;
}

export function resolveCurrentUsdExportMode({
  isHydrating,
  hasPreparedExportCache,
  hasSceneSnapshot,
}: ResolveCurrentUsdExportModeOptions): CurrentUsdExportMode {
  if (!isHydrating && (hasPreparedExportCache || hasSceneSnapshot)) {
    return 'bundle';
  }

  return 'unavailable';
}
