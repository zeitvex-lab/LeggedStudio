import { logRuntimeFailure } from '@/core/utils/runtimeDiagnostics';
import { getUsdRuntimeEnvironmentError } from '@/features/editor/usd_runtime';
import type { RobotFile } from '@/types';

type StageOpenSourceFile = Pick<RobotFile, 'name' | 'content' | 'blobUrl' | 'format'>;
type StageOpenAvailableFile = Pick<RobotFile, 'name' | 'content' | 'blobUrl' | 'format'>;

interface UsdSelectionPrewarmDependencies {
  prewarmMainThreadRuntime: () => void;
  prewarmOffscreenRuntime: () => void;
  prewarmStageOpen: (
    file: StageOpenSourceFile,
    availableFiles: StageOpenAvailableFile[],
    assets: Record<string, string>,
  ) => void;
  hasBlobBackedLargeUsdaInStageScope: (
    file: StageOpenSourceFile,
    availableFiles: StageOpenAvailableFile[],
  ) => boolean;
  getRuntimeEnvironmentError?: () => Error | null;
}

interface UsdSelectionBackgroundPrewarmDependencies {
  loadHandler: () => Promise<ReturnType<typeof createUsdSelectionPrewarmHandler>>;
  getRuntimeEnvironmentError?: () => Error | null;
  logFailure?: typeof logRuntimeFailure;
}

export function createUsdSelectionPrewarmHandler({
  prewarmMainThreadRuntime,
  prewarmOffscreenRuntime,
  prewarmStageOpen,
  hasBlobBackedLargeUsdaInStageScope,
  getRuntimeEnvironmentError = getUsdRuntimeEnvironmentError,
}: UsdSelectionPrewarmDependencies): (
  file: StageOpenSourceFile,
  availableFiles: StageOpenAvailableFile[],
  assets: Record<string, string>,
) => void {
  return (file, availableFiles, assets) => {
    if (file.format !== 'usd') {
      return;
    }

    if (getRuntimeEnvironmentError()) {
      return;
    }

    prewarmMainThreadRuntime();
    prewarmOffscreenRuntime();

    if (hasBlobBackedLargeUsdaInStageScope(file, availableFiles)) {
      return;
    }

    prewarmStageOpen(file, availableFiles, assets);
  };
}

let usdSelectionPrewarmHandlerPromise: Promise<
  ReturnType<typeof createUsdSelectionPrewarmHandler>
> | null = null;

function loadUsdSelectionPrewarmHandler() {
  if (!usdSelectionPrewarmHandlerPromise) {
    usdSelectionPrewarmHandlerPromise = Promise.all([
      import('@/features/editor/usd_prewarm'),
      import('@/features/editor/usd_offscreen_runtime'),
      import('@/features/editor/usd_runtime'),
    ])
      .then(([usdPrewarm, offscreenRuntime, mainThreadRuntime]) =>
        createUsdSelectionPrewarmHandler({
          hasBlobBackedLargeUsdaInStageScope: usdPrewarm.hasBlobBackedLargeUsdaInStageScope,
          prewarmMainThreadRuntime: mainThreadRuntime.prewarmUsdWasmRuntimeInBackground,
          prewarmOffscreenRuntime: offscreenRuntime.prewarmUsdOffscreenViewerRuntimeInBackground,
          prewarmStageOpen: usdPrewarm.prewarmPreparedUsdStageOpenDataInBackground,
        }),
      )
      .catch((error) => {
        usdSelectionPrewarmHandlerPromise = null;
        throw error;
      });
  }

  return usdSelectionPrewarmHandlerPromise;
}

export function createUsdSelectionBackgroundPrewarm({
  loadHandler,
  getRuntimeEnvironmentError = getUsdRuntimeEnvironmentError,
  logFailure = logRuntimeFailure,
}: UsdSelectionBackgroundPrewarmDependencies): (
  file: StageOpenSourceFile,
  availableFiles: StageOpenAvailableFile[],
  assets: Record<string, string>,
) => void {
  return (file, availableFiles, assets) => {
    if (file.format !== 'usd') {
      return;
    }

    if (getRuntimeEnvironmentError()) {
      return;
    }

    void loadHandler()
      .then((prewarm) => prewarm(file, availableFiles, assets))
      .catch((error) => {
        logFailure('prewarmUsdSelectionInBackground', error, 'warn');
      });
  };
}

const prewarmUsdSelectionInBackgroundImpl = createUsdSelectionBackgroundPrewarm({
  loadHandler: loadUsdSelectionPrewarmHandler,
});

export function prewarmUsdSelectionInBackground(
  file: StageOpenSourceFile,
  availableFiles: StageOpenAvailableFile[],
  assets: Record<string, string>,
): void {
  prewarmUsdSelectionInBackgroundImpl(file, availableFiles, assets);
}
