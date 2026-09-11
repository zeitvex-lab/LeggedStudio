export function waitForNextPaint(): Promise<void> {
  if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      // Wait through a full paint so transient progress HUDs can become visible
      // before the next synchronous phase starts blocking the main thread.
      window.requestAnimationFrame(() => resolve());
    });
  });
}
