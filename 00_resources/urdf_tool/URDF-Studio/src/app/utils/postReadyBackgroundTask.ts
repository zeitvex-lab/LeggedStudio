export const POST_READY_BACKGROUND_DELAY_MS = 0;
export const POST_READY_BACKGROUND_IDLE_TIMEOUT_MS = 2_000;

export interface PostReadyBackgroundTaskScheduler {
  setTimeout: (callback: () => void, delayMs: number) => number;
  clearTimeout: (handle: number) => void;
  requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
}

function getDefaultScheduler(): PostReadyBackgroundTaskScheduler {
  return {
    setTimeout: (callback, delayMs) => window.setTimeout(callback, delayMs),
    clearTimeout: (handle) => window.clearTimeout(handle),
    requestIdleCallback: window.requestIdleCallback?.bind(window),
    cancelIdleCallback: window.cancelIdleCallback?.bind(window),
  };
}

export function schedulePostReadyBackgroundTask(
  run: () => void,
  options: {
    delayMs?: number;
    idleTimeoutMs?: number;
    scheduler?: PostReadyBackgroundTaskScheduler;
  } = {},
): () => void {
  const scheduler = options.scheduler ?? getDefaultScheduler();
  const delayMs = options.delayMs ?? POST_READY_BACKGROUND_DELAY_MS;
  const idleTimeoutMs = options.idleTimeoutMs ?? POST_READY_BACKGROUND_IDLE_TIMEOUT_MS;
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
