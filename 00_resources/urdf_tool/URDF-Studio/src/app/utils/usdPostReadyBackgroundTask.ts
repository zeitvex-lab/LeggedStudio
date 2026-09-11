export const USD_POST_READY_BACKGROUND_DELAY_MS = 8_000;
export const USD_POST_READY_BACKGROUND_IDLE_TIMEOUT_MS = 15_000;
export const USD_POST_READY_AUTO_EXPORT_CACHE_POSITION_LIMIT = 1_000_000;

export interface UsdPostReadyBackgroundTaskScheduler {
  setTimeout: (callback: () => void, delayMs: number) => number;
  clearTimeout: (handle: number) => void;
  requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
}

function getDefaultScheduler(): UsdPostReadyBackgroundTaskScheduler {
  return {
    setTimeout: (callback, delayMs) => window.setTimeout(callback, delayMs),
    clearTimeout: (handle) => window.clearTimeout(handle),
    requestIdleCallback: window.requestIdleCallback?.bind(window),
    cancelIdleCallback: window.cancelIdleCallback?.bind(window),
  };
}

export function scheduleUsdPostReadyBackgroundTask(
  run: () => void,
  options: {
    delayMs?: number;
    idleTimeoutMs?: number;
    scheduler?: UsdPostReadyBackgroundTaskScheduler;
  } = {},
): () => void {
  const scheduler = options.scheduler ?? getDefaultScheduler();
  const delayMs = options.delayMs ?? USD_POST_READY_BACKGROUND_DELAY_MS;
  const idleTimeoutMs = options.idleTimeoutMs ?? USD_POST_READY_BACKGROUND_IDLE_TIMEOUT_MS;
  let cancelled = false;
  let delayHandle: number | null = null;
  let idleHandle: number | null = null;
  let fallbackHandle: number | null = null;

  const runOnce = () => {
    if (cancelled) {
      return;
    }
    cancelled = true;
    run();
  };

  delayHandle = scheduler.setTimeout(() => {
    delayHandle = null;
    if (cancelled) {
      return;
    }

    if (scheduler.requestIdleCallback && scheduler.cancelIdleCallback) {
      idleHandle = scheduler.requestIdleCallback(runOnce, { timeout: idleTimeoutMs });
      return;
    }

    fallbackHandle = scheduler.setTimeout(runOnce, 0);
  }, delayMs);

  return () => {
    if (cancelled) {
      return;
    }
    cancelled = true;
    if (delayHandle !== null) {
      scheduler.clearTimeout(delayHandle);
      delayHandle = null;
    }
    if (idleHandle !== null) {
      scheduler.cancelIdleCallback?.(idleHandle);
      idleHandle = null;
    }
    if (fallbackHandle !== null) {
      scheduler.clearTimeout(fallbackHandle);
      fallbackHandle = null;
    }
  };
}

export function shouldAutoPrepareUsdPostReadyExportCache(
  sceneSnapshot:
    | {
        buffers?: {
          positions?: { length?: number } | null;
        } | null;
      }
    | null
    | undefined,
): boolean {
  const positionCount = Number(sceneSnapshot?.buffers?.positions?.length ?? 0);
  return positionCount <= USD_POST_READY_AUTO_EXPORT_CACHE_POSITION_LIMIT;
}
