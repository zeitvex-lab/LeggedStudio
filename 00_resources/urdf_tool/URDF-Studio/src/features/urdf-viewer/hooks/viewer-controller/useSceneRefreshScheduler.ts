import { useCallback, useEffect, useRef } from 'react';

export interface SceneRefreshOptions {
  force?: boolean;
}

type SceneRefreshCallback = (options?: SceneRefreshOptions) => void;

export function useSceneRefreshScheduler() {
  const sceneRefreshRef = useRef<SceneRefreshCallback | null>(null);
  const pendingFrameRef = useRef<number | null>(null);
  const pendingForceRef = useRef(false);

  const flushSceneRefresh = useCallback(() => {
    pendingFrameRef.current = null;
    const force = pendingForceRef.current;
    pendingForceRef.current = false;
    sceneRefreshRef.current?.(force ? { force: true } : undefined);
  }, []);

  const cancelSceneRefresh = useCallback(() => {
    if (pendingFrameRef.current !== null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(pendingFrameRef.current);
      pendingFrameRef.current = null;
    }
    pendingForceRef.current = false;
  }, []);

  const requestSceneRefresh = useCallback(
    (options?: SceneRefreshOptions) => {
      if (options?.force) {
        pendingForceRef.current = true;
      }

      // Coalesce same-frame callers while preserving any force=true request.
      if (pendingFrameRef.current !== null) {
        return;
      }

      if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
        flushSceneRefresh();
        return;
      }

      pendingFrameRef.current = window.requestAnimationFrame(() => {
        flushSceneRefresh();
      });
    },
    [flushSceneRefresh],
  );

  const registerSceneRefresh = useCallback((refreshScene: SceneRefreshCallback | null) => {
    sceneRefreshRef.current = refreshScene;
  }, []);

  useEffect(() => cancelSceneRefresh, [cancelSceneRefresh]);

  return {
    requestSceneRefresh,
    registerSceneRefresh,
    cancelSceneRefresh,
  };
}
