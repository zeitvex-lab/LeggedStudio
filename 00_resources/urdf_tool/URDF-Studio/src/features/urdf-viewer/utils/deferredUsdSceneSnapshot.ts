export const USD_DEFERRED_SCENE_SNAPSHOT_INITIAL_DELAY_MS = 1_200;
export const USD_DEFERRED_SCENE_SNAPSHOT_INTERACTION_IDLE_MS = 900;
export const USD_DEFERRED_SCENE_SNAPSHOT_MAX_DELAY_MS = 10_000;

export interface DeferredUsdSceneSnapshotDelayOptions {
  activeInteraction?: boolean;
  initialDelayMs?: number;
  interactionIdleMs?: number;
  lastInteractionAt: number;
  maxDelayMs?: number;
  now: number;
  requestedAt: number;
}

function clampNonNegative(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function resolveDeferredUsdSceneSnapshotDelayMs({
  activeInteraction = false,
  initialDelayMs = USD_DEFERRED_SCENE_SNAPSHOT_INITIAL_DELAY_MS,
  interactionIdleMs = USD_DEFERRED_SCENE_SNAPSHOT_INTERACTION_IDLE_MS,
  lastInteractionAt,
  maxDelayMs = USD_DEFERRED_SCENE_SNAPSHOT_MAX_DELAY_MS,
  now,
  requestedAt,
}: DeferredUsdSceneSnapshotDelayOptions): number {
  const elapsedMs = clampNonNegative(now - requestedAt);
  const remainingInitialDelayMs = clampNonNegative(initialDelayMs - elapsedMs);
  if (remainingInitialDelayMs > 0) {
    return remainingInitialDelayMs;
  }

  if (activeInteraction) {
    return interactionIdleMs;
  }

  const timeSinceInteractionMs =
    lastInteractionAt > 0 ? clampNonNegative(now - lastInteractionAt) : Number.POSITIVE_INFINITY;
  if (timeSinceInteractionMs < interactionIdleMs && elapsedMs < maxDelayMs) {
    return Math.max(16, interactionIdleMs - timeSinceInteractionMs);
  }

  return 0;
}
