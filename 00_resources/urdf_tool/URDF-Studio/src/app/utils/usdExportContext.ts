import type { RobotState, UsdPreparedExportCache } from '@/types';
import {
  buildUsdExportBundleFromPreparedCache,
  buildUsdExportBundleFromSnapshot,
  resolveUsdExportSceneSnapshot,
  type UsdExportBundle,
} from '@/features/editor/usd_export';

type ResolveUsdExportSceneSnapshotOptions = NonNullable<
  Parameters<typeof resolveUsdExportSceneSnapshot>[0]
>;

export interface ResolveCurrentUsdExportBundleOptions {
  stageSourcePath: string;
  currentRobot: RobotState;
  cachedSnapshot?: unknown | null;
  preparedCache?: UsdPreparedExportCache | null;
  targetWindow?: ResolveUsdExportSceneSnapshotOptions['targetWindow'];
}

export function resolveCurrentUsdExportBundle({
  stageSourcePath,
  currentRobot,
  cachedSnapshot = null,
  preparedCache = null,
  targetWindow,
}: ResolveCurrentUsdExportBundleOptions): UsdExportBundle | null {
  const snapshot = resolveUsdExportSceneSnapshot({
    stageSourcePath,
    cachedSnapshot: cachedSnapshot as ResolveUsdExportSceneSnapshotOptions['cachedSnapshot'],
    targetWindow,
  });

  if (preparedCache) {
    const preparedBundle = buildUsdExportBundleFromPreparedCache(preparedCache, {
      currentRobot,
    });
    if (preparedBundle) {
      return preparedBundle;
    }
  }

  if (snapshot) {
    const snapshotBundle = buildUsdExportBundleFromSnapshot(snapshot, {
      fileName: stageSourcePath,
      currentRobot,
      targetWindow,
    });
    if (snapshotBundle) {
      return snapshotBundle;
    }
  }

  return null;
}
