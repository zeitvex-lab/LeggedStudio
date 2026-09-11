type PendingUsdCacheFlusher = (() => void) | null;

let pendingUsdCacheFlusher: PendingUsdCacheFlusher = null;

export function registerPendingUsdCacheFlusher(flusher: PendingUsdCacheFlusher) {
  pendingUsdCacheFlusher = flusher;
}

export function flushPendingUsdCache() {
  pendingUsdCacheFlusher?.();
}
