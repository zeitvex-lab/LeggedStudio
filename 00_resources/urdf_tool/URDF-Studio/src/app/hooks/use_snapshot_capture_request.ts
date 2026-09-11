import { useCallback, useEffect, useRef } from 'react';
import {
  createSnapshotCaptureAbortError,
  isSnapshotCaptureAbortError,
  type SnapshotCaptureAction,
  type SnapshotCaptureOptions,
  type SnapshotCaptureProgress,
} from '@/shared/components/3d';
import { logRegressionError } from '@/shared/debug/consoleDiagnostics';
import { resolveSnapshotCaptureAction } from '../components/snapshot-preview/resolveSnapshotCaptureAction';
import type { SnapshotPreviewSession } from '../components/snapshot-preview/types';

interface SnapshotCaptureActionRef {
  current: SnapshotCaptureAction | null;
}

interface UseSnapshotCaptureRequestParams {
  liveCaptureActionRef: SnapshotCaptureActionRef;
  frozenPreviewCaptureActionRef: SnapshotCaptureActionRef;
  snapshotPreviewSession: SnapshotPreviewSession | null;
  setIsSnapshotCapturing: (isCapturing: boolean) => void;
  setSnapshotCaptureProgress: (progress: SnapshotCaptureProgress | null) => void;
  showToast: (message: string, type?: 'info' | 'success') => void;
  snapshotFailedMessage: string;
}

export function useSnapshotCaptureRequest({
  liveCaptureActionRef,
  frozenPreviewCaptureActionRef,
  snapshotPreviewSession,
  setIsSnapshotCapturing,
  setSnapshotCaptureProgress,
  showToast,
  snapshotFailedMessage,
}: UseSnapshotCaptureRequestParams) {
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  useEffect(
    () => () => {
      abortControllerRef.current?.abort(createSnapshotCaptureAbortError());
      abortControllerRef.current = null;
    },
    [],
  );

  const handleCancelSnapshotCapture = useCallback(() => {
    abortControllerRef.current?.abort(createSnapshotCaptureAbortError());
  }, []);

  const handleCaptureSnapshot = useCallback(
    async (options: SnapshotCaptureOptions) => {
      const resolvedCaptureAction = resolveSnapshotCaptureAction({
        liveCaptureAction: liveCaptureActionRef.current,
        frozenPreviewCaptureAction: frozenPreviewCaptureActionRef.current,
        preferFrozenPreviewCapture: Boolean(snapshotPreviewSession),
      });

      if (!resolvedCaptureAction) {
        showToast(snapshotFailedMessage, 'info');
        return;
      }

      const abortController = new AbortController();
      abortControllerRef.current?.abort(createSnapshotCaptureAbortError());
      abortControllerRef.current = abortController;
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      const publishProgress = (progress: SnapshotCaptureProgress | null) => {
        if (requestIdRef.current !== requestId || abortController.signal.aborted) {
          return;
        }

        setSnapshotCaptureProgress(progress);
      };

      try {
        setIsSnapshotCapturing(true);
        publishProgress({ phase: 'preparing', progress: 0.02 });
        await resolvedCaptureAction.action({
          ...options,
          cameraSnapshot:
            resolvedCaptureAction.source === 'live'
              ? (snapshotPreviewSession?.cameraSnapshot ?? null)
              : null,
          signal: abortController.signal,
          onProgress: publishProgress,
        });
      } catch (error) {
        if (abortController.signal.aborted || isSnapshotCaptureAbortError(error)) {
          return;
        }

        logRegressionError('Snapshot failed:', error);
        showToast(snapshotFailedMessage, 'info');
      } finally {
        if (requestIdRef.current === requestId) {
          abortControllerRef.current = null;
          setSnapshotCaptureProgress(null);
          setIsSnapshotCapturing(false);
        }
      }
    },
    [
      frozenPreviewCaptureActionRef,
      liveCaptureActionRef,
      setIsSnapshotCapturing,
      setSnapshotCaptureProgress,
      showToast,
      snapshotFailedMessage,
      snapshotPreviewSession,
    ],
  );

  return {
    handleCaptureSnapshot,
    handleCancelSnapshotCapture,
  };
}
