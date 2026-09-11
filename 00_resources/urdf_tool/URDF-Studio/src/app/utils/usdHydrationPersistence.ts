import type { ViewerRobotDataResolution } from '@/features/editor/usd_hydration';
import type { RobotData, UsdBakedScene, UsdPreparedExportCache, UsdSceneSnapshot } from '@/types';

interface UsdHydrationResolutionLike {
  robotData: RobotData;
  stageSourcePath?: string | null;
  usdBakedScene?: UsdBakedScene | null;
  usdSceneSnapshot?: UsdSceneSnapshot | null;
}

interface UsdHydrationPersistencePlanOptions {
  resolution: UsdHydrationResolutionLike;
  existingSceneSnapshot?: unknown | null;
  existingPreparedExportCache?: unknown | null;
}

export interface UsdHydrationPersistencePlan {
  bakedScene: unknown | null;
  sceneSnapshot: unknown | null;
  shouldSeedBakedScene: boolean;
  shouldSeedSceneSnapshot: boolean;
  shouldSeedPreparedExportCache: boolean;
}

export interface ResolvedUsdHydrationRobotData {
  robotData: RobotData;
  preparedExportCache: UsdPreparedExportCache | null;
}

interface ResolveUsdHydrationRobotDataOptions {
  resolution: ViewerRobotDataResolution & UsdHydrationResolutionLike;
  allowSynchronousPreparedCacheFromSnapshot?: boolean;
  existingPreparedExportCache?: UsdPreparedExportCache | null;
  prepareExportCacheFromSnapshot: (
    snapshot: UsdSceneSnapshot,
    options?: {
      fileName?: string;
      resolution?: ViewerRobotDataResolution | null;
    },
  ) => UsdPreparedExportCache | null;
}

export function buildUsdHydrationPersistencePlan({
  resolution,
  existingSceneSnapshot = null,
  existingPreparedExportCache = null,
}: UsdHydrationPersistencePlanOptions): UsdHydrationPersistencePlan {
  const resolvedBakedScene =
    existingSceneSnapshot ?? resolution.usdBakedScene ?? resolution.usdSceneSnapshot ?? null;
  const shouldSeedBakedScene =
    existingSceneSnapshot == null &&
    (resolution.usdBakedScene != null || resolution.usdSceneSnapshot != null);

  return {
    bakedScene: resolvedBakedScene,
    sceneSnapshot: resolvedBakedScene,
    shouldSeedBakedScene,
    shouldSeedSceneSnapshot: shouldSeedBakedScene,
    shouldSeedPreparedExportCache:
      existingPreparedExportCache == null && resolvedBakedScene != null,
  };
}

export function resolveUsdHydrationRobotData({
  resolution,
  allowSynchronousPreparedCacheFromSnapshot = true,
  existingPreparedExportCache = null,
  prepareExportCacheFromSnapshot,
}: ResolveUsdHydrationRobotDataOptions): ResolvedUsdHydrationRobotData {
  const bakedScene = resolution.usdBakedScene ?? resolution.usdSceneSnapshot ?? null;

  // Fresh worker snapshots should outrank any previously prepared cache for the
  // same file path. Reusing cached RobotData here can rehydrate a newer USD
  // import with stale mesh assignments or transforms until the deferred full
  // scene snapshot arrives.
  if (!bakedScene && existingPreparedExportCache?.robotData) {
    return {
      robotData: existingPreparedExportCache.robotData,
      preparedExportCache: existingPreparedExportCache,
    };
  }

  if (bakedScene && allowSynchronousPreparedCacheFromSnapshot) {
    const preparedExportCache = prepareExportCacheFromSnapshot(bakedScene, {
      fileName: resolution.stageSourcePath || bakedScene.stageSourcePath || undefined,
      resolution,
    });
    if (preparedExportCache?.robotData) {
      return {
        robotData: preparedExportCache.robotData,
        preparedExportCache,
      };
    }
  }

  return {
    robotData: resolution.robotData,
    preparedExportCache: null,
  };
}
