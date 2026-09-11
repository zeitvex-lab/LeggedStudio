import { isRegressionDebugEnabled } from './regressionDebugEnabled';

export type UsdStageLoadDebugStatus = 'pending' | 'resolved' | 'rejected';

export interface UsdStageLoadDebugEntry {
  sourceFileName: string;
  step: string;
  status: UsdStageLoadDebugStatus;
  timestamp: number;
  durationMs?: number;
  detail?: Record<string, unknown> | null;
}

const USD_STAGE_LOAD_DEBUG_HISTORY_LIMIT = 24;
export const USD_STAGE_LOAD_BASELINE_STEPS = [
  'ensure-runtime',
  'prepare-stage-open-data',
  'load-usd-stage',
  'resolve-runtime-robot-data',
  'ready',
] as const;
export type UsdStageLoadBaselineStep = (typeof USD_STAGE_LOAD_BASELINE_STEPS)[number];

type RuntimeWindowWithDebug = Window & {
  __usdStageLoadDebug?: UsdStageLoadDebugEntry;
  __usdStageLoadDebugHistory?: UsdStageLoadDebugEntry[];
};

export interface UsdStageLoadBaselineDurations {
  sourceFileName: string;
  steps: Record<UsdStageLoadBaselineStep, number | null>;
}

export function recordUsdStageLoadDebug(entry: UsdStageLoadDebugEntry): void {
  if (typeof window === 'undefined' || !isRegressionDebugEnabled(window)) {
    return;
  }

  const runtimeWindow = window as RuntimeWindowWithDebug;
  runtimeWindow.__usdStageLoadDebug = entry;
  const history = Array.isArray(runtimeWindow.__usdStageLoadDebugHistory)
    ? runtimeWindow.__usdStageLoadDebugHistory.slice(-(USD_STAGE_LOAD_DEBUG_HISTORY_LIMIT - 1))
    : [];
  history.push(entry);
  runtimeWindow.__usdStageLoadDebugHistory = history;
}

export function getUsdStageLoadDebugHistoryForFile(
  targetWindow: Window,
  fileName: string,
): UsdStageLoadDebugEntry[] {
  const runtimeWindow = targetWindow as RuntimeWindowWithDebug;
  if (!Array.isArray(runtimeWindow.__usdStageLoadDebugHistory)) {
    return [];
  }

  return runtimeWindow.__usdStageLoadDebugHistory.filter(
    (entry) => entry?.sourceFileName === fileName,
  );
}

export function getLatestUsdStageLoadDebugEntry(
  targetWindow: Window,
  fileName: string,
  step: string,
  status?: UsdStageLoadDebugStatus,
): UsdStageLoadDebugEntry | null {
  const history = getUsdStageLoadDebugHistoryForFile(targetWindow, fileName);
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const entry = history[index];
    if (entry.step !== step) {
      continue;
    }
    if (status && entry.status !== status) {
      continue;
    }
    return entry;
  }

  return null;
}

export function getUsdStageLoadBaselineDurations(
  targetWindow: Window,
  fileName: string,
): UsdStageLoadBaselineDurations {
  const steps = Object.fromEntries(
    USD_STAGE_LOAD_BASELINE_STEPS.map((step) => {
      const entry = getLatestUsdStageLoadDebugEntry(targetWindow, fileName, step, 'resolved');
      return [step, typeof entry?.durationMs === 'number' ? entry.durationMs : null];
    }),
  ) as Record<UsdStageLoadBaselineStep, number | null>;

  return {
    sourceFileName: fileName,
    steps,
  };
}
