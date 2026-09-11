import { isRegressionDebugEnabled } from './regressionDebugEnabled';

export type VisualizerCollisionLoadDebugPhase =
  | 'show-requested'
  | 'reveal-progress'
  | 'reveal-complete';

export interface VisualizerCollisionLoadDebugEntry {
  sessionId: string;
  signature: string;
  phase: VisualizerCollisionLoadDebugPhase;
  timestamp: number;
  durationMs?: number;
  detail?: Record<string, unknown> | null;
}

const VISUALIZER_COLLISION_LOAD_DEBUG_HISTORY_LIMIT = 48;

type RuntimeWindowWithDebug = Window & {
  __visualizerCollisionLoadDebug?: VisualizerCollisionLoadDebugEntry;
  __visualizerCollisionLoadDebugHistory?: VisualizerCollisionLoadDebugEntry[];
};

export function recordVisualizerCollisionLoadDebug(entry: VisualizerCollisionLoadDebugEntry): void {
  if (typeof window === 'undefined' || !isRegressionDebugEnabled(window)) {
    return;
  }

  const runtimeWindow = window as RuntimeWindowWithDebug;
  runtimeWindow.__visualizerCollisionLoadDebug = entry;
  const history = Array.isArray(runtimeWindow.__visualizerCollisionLoadDebugHistory)
    ? runtimeWindow.__visualizerCollisionLoadDebugHistory.slice(
        -(VISUALIZER_COLLISION_LOAD_DEBUG_HISTORY_LIMIT - 1),
      )
    : [];
  history.push(entry);
  runtimeWindow.__visualizerCollisionLoadDebugHistory = history;
}

export function getVisualizerCollisionLoadDebugHistory(
  targetWindow: Window,
  signature?: string,
): VisualizerCollisionLoadDebugEntry[] {
  const runtimeWindow = targetWindow as RuntimeWindowWithDebug;
  if (!Array.isArray(runtimeWindow.__visualizerCollisionLoadDebugHistory)) {
    return [];
  }

  if (!signature) {
    return runtimeWindow.__visualizerCollisionLoadDebugHistory;
  }

  return runtimeWindow.__visualizerCollisionLoadDebugHistory.filter(
    (entry) => entry?.signature === signature,
  );
}

export function getLatestVisualizerCollisionLoadDebugEntry(
  targetWindow: Window,
  phase: VisualizerCollisionLoadDebugPhase,
  signature?: string,
): VisualizerCollisionLoadDebugEntry | null {
  const history = getVisualizerCollisionLoadDebugHistory(targetWindow, signature);
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const entry = history[index];
    if (entry.phase === phase) {
      return entry;
    }
  }

  return null;
}
