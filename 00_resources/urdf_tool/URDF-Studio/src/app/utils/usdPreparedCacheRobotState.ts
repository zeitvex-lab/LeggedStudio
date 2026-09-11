import type { RobotData, UsdPreparedExportCache } from '@/types';

export type UsdPreparedCacheRobotStateUpdate =
  | {
      status: 'updated';
      preparedExportCache: UsdPreparedExportCache;
    }
  | {
      status: 'missing-cache';
      preparedExportCache: null;
    };

interface ResolveUsdPreparedCacheRobotStateUpdateOptions {
  existingPreparedExportCache: UsdPreparedExportCache | null;
  robotData: RobotData;
}

export function resolveUsdPreparedCacheRobotStateUpdate({
  existingPreparedExportCache,
  robotData,
}: ResolveUsdPreparedCacheRobotStateUpdateOptions): UsdPreparedCacheRobotStateUpdate {
  if (!existingPreparedExportCache) {
    return {
      status: 'missing-cache',
      preparedExportCache: null,
    };
  }

  return {
    status: 'updated',
    preparedExportCache: {
      ...existingPreparedExportCache,
      robotData,
    },
  };
}
