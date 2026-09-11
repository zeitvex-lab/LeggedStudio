export type UsdProgressEvent<TPhase extends string = string> = {
  phase: TPhase;
  completed: number;
  total: number;
  label?: string;
};

export type UsdProgressTracker<TPhase extends string = string> = {
  phase: TPhase;
  completed: number;
  total: number;
  onProgress?: (progress: UsdProgressEvent<TPhase>) => void;
};

export const isUsdExportRunningInWorkerScope = (): boolean => {
  if (typeof WorkerGlobalScope === 'undefined') {
    return false;
  }

  return globalThis instanceof WorkerGlobalScope;
};

export const yieldToMainThread = async (): Promise<void> => {
  // USD export already runs inside a dedicated worker in the app path.
  // Yielding there via setTimeout(0) turns large mesh serialization into
  // repeated sleeps and leaves CPU underutilized, so keep cooperative yields
  // only for main-thread callers.
  if (isUsdExportRunningInWorkerScope()) {
    return;
  }

  await new Promise<void>((resolve) => {
    if (typeof globalThis.requestAnimationFrame === 'function') {
      globalThis.requestAnimationFrame(() => resolve());
      return;
    }

    globalThis.setTimeout(resolve, 0);
  });
};

export const yieldPeriodically = async (index: number, interval: number): Promise<void> => {
  if (interval > 0 && index > 0 && index % interval === 0) {
    await yieldToMainThread();
  }
};

export const normalizeUsdProgressLabel = (
  value: string | null | undefined,
  fallback: string,
): string => {
  const normalized = String(value || '').trim();
  return normalized.length > 0 ? normalized : fallback;
};

export const createUsdProgressTracker = <TPhase extends string>(
  phase: TPhase,
  total: number,
  onProgress?: (progress: UsdProgressEvent<TPhase>) => void,
): UsdProgressTracker<TPhase> => {
  const tracker: UsdProgressTracker<TPhase> = {
    phase,
    completed: 0,
    total,
    onProgress,
  };

  if (onProgress && total > 0) {
    onProgress({
      phase,
      completed: 0,
      total,
    });
  }

  return tracker;
};

export const advanceUsdProgress = <TPhase extends string>(
  tracker: UsdProgressTracker<TPhase> | null | undefined,
  label?: string,
): void => {
  if (!tracker || tracker.total <= 0) {
    return;
  }

  tracker.completed = Math.min(tracker.total, tracker.completed + 1);
  tracker.onProgress?.({
    phase: tracker.phase,
    completed: tracker.completed,
    total: tracker.total,
    ...(label ? { label } : {}),
  });
};
