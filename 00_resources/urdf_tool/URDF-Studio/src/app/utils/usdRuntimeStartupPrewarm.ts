import { logRuntimeFailure } from '@/core/utils/runtimeDiagnostics';
import { getUsdRuntimeEnvironmentError } from '@/features/editor/usd_runtime';
import { scheduleUsdPostReadyBackgroundTask } from './usdPostReadyBackgroundTask';
import type { UsdPostReadyBackgroundTaskScheduler } from './usdPostReadyBackgroundTask';

interface UsdRuntimeStartupPrewarmDependencies {
  prewarmMainThreadRuntime: () => void;
  prewarmOffscreenRuntime: () => void;
}

interface UsdRuntimeStartupBackgroundPrewarmDependencies {
  loadMainThreadRuntime: () => Promise<{ prewarmUsdWasmRuntimeInBackground: () => void }>;
  loadOffscreenRuntime: () => Promise<{
    prewarmUsdOffscreenViewerRuntimeInBackground: () => void;
  }>;
  getRuntimeEnvironmentError?: () => Error | null;
  logFailure?: typeof logRuntimeFailure;
}

interface NetworkInformationLike {
  effectiveType?: string;
  saveData?: boolean;
}

interface DocumentVisibilityLike {
  readyState?: DocumentReadyState;
  visibilityState?: DocumentVisibilityState;
}

interface WindowLoadTargetLike {
  addEventListener: (type: 'load', listener: () => void, options?: { once?: boolean }) => void;
  removeEventListener: (type: 'load', listener: () => void) => void;
}

interface UsdRuntimeStartupIdlePrewarmOptions {
  connection?: NetworkInformationLike | null;
  delayMs?: number;
  document?: DocumentVisibilityLike | null;
  idleTimeoutMs?: number;
  loadTarget?: WindowLoadTargetLike | null;
  prewarm?: () => void;
  scheduler?: UsdPostReadyBackgroundTaskScheduler;
}

export function createUsdRuntimeStartupPrewarmHandler({
  prewarmMainThreadRuntime,
  prewarmOffscreenRuntime,
}: UsdRuntimeStartupPrewarmDependencies): () => void {
  let started = false;

  return () => {
    if (started) {
      return;
    }

    started = true;
    prewarmMainThreadRuntime();
    prewarmOffscreenRuntime();
  };
}

export function createUsdRuntimeStartupBackgroundPrewarm({
  loadMainThreadRuntime,
  loadOffscreenRuntime,
  getRuntimeEnvironmentError = getUsdRuntimeEnvironmentError,
  logFailure = logRuntimeFailure,
}: UsdRuntimeStartupBackgroundPrewarmDependencies): () => void {
  let prewarmPromise: Promise<void> | null = null;

  return () => {
    if (!prewarmPromise) {
      const runtimeEnvironmentError = getRuntimeEnvironmentError();
      if (runtimeEnvironmentError) {
        prewarmPromise = Promise.resolve();
        return;
      }

      prewarmPromise = Promise.all([loadMainThreadRuntime(), loadOffscreenRuntime()])
        .then(([mainThreadRuntime, offscreenRuntime]) => {
          mainThreadRuntime.prewarmUsdWasmRuntimeInBackground();
          offscreenRuntime.prewarmUsdOffscreenViewerRuntimeInBackground();
        })
        .catch((error) => {
          logFailure('prewarmUsdViewerRuntimesInBackground', error, 'warn');
          prewarmPromise = null;
        });
    }
  };
}

const prewarmUsdViewerRuntimesInBackgroundImpl = createUsdRuntimeStartupBackgroundPrewarm({
  loadMainThreadRuntime: () => import('@/features/editor/usd_runtime'),
  loadOffscreenRuntime: () => import('@/features/editor/usd_offscreen_runtime'),
});

export function prewarmUsdViewerRuntimesInBackground(): void {
  prewarmUsdViewerRuntimesInBackgroundImpl();
}

function getNavigatorConnection(): NetworkInformationLike | null {
  if (typeof navigator === 'undefined') {
    return null;
  }

  return (navigator as Navigator & { connection?: NetworkInformationLike }).connection ?? null;
}

function getDocumentVisibility(): DocumentVisibilityLike | null {
  if (typeof document === 'undefined') {
    return null;
  }

  return document;
}

function getWindowLoadTarget(): WindowLoadTargetLike | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return {
    addEventListener: (type, listener, options) => {
      window.addEventListener(type, listener, options);
    },
    removeEventListener: (type, listener) => {
      window.removeEventListener(type, listener);
    },
  };
}

export function shouldSkipUsdRuntimeStartupIdlePrewarm(
  connection: NetworkInformationLike | null | undefined,
): boolean {
  if (connection?.saveData) {
    return true;
  }

  return connection?.effectiveType === 'slow-2g' || connection?.effectiveType === '2g';
}

export function scheduleUsdRuntimeStartupIdlePrewarm({
  connection = getNavigatorConnection(),
  delayMs,
  document: visibilityDocument = getDocumentVisibility(),
  idleTimeoutMs,
  loadTarget = getWindowLoadTarget(),
  prewarm = prewarmUsdViewerRuntimesInBackground,
  scheduler,
}: UsdRuntimeStartupIdlePrewarmOptions = {}): () => void {
  if (shouldSkipUsdRuntimeStartupIdlePrewarm(connection)) {
    return () => {};
  }

  const schedulePrewarm = () =>
    scheduleUsdPostReadyBackgroundTask(
      () => {
        if (visibilityDocument?.visibilityState === 'hidden') {
          return;
        }

        prewarm();
      },
      {
        delayMs,
        idleTimeoutMs,
        scheduler,
      },
    );

  if (
    visibilityDocument?.readyState &&
    visibilityDocument.readyState !== 'complete' &&
    loadTarget
  ) {
    let cancelScheduledPrewarm: (() => void) | null = null;
    const handleLoad = () => {
      cancelScheduledPrewarm = schedulePrewarm();
    };

    loadTarget.addEventListener('load', handleLoad, { once: true });

    return () => {
      loadTarget.removeEventListener('load', handleLoad);
      cancelScheduledPrewarm?.();
    };
  }

  return schedulePrewarm();
}
