/**
 * useSnapshot Hook
 * Handle snapshot capture operations
 * Works with SnapshotManager component from shared/components/3d
 */

import { useCallback, useRef } from 'react';
import { translations } from '@/shared/i18n';
import { useUIStore } from '@/store';

interface UseSnapshotOptions {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
  showToast?: (message: string, type: 'info' | 'success' | 'error') => void;
}

interface UseSnapshotReturn {
  snapshotActionRef: React.RefObject<(() => void) | null>;
  handleSnapshot: () => void;
}

export function useSnapshot(options: UseSnapshotOptions = {}): UseSnapshotReturn {
  const { onSuccess, onError, showToast } = options;
  const lang = useUIStore((s) => s.lang);
  const t = translations[lang];
  const snapshotActionRef = useRef<(() => void) | null>(null);

  const handleSnapshot = useCallback(() => {
    if (snapshotActionRef.current) {
      try {
        // Trigger the snapshot logic inside the Three.js context
        snapshotActionRef.current();
        // Show progress toast
        showToast?.(t.generatingSnapshot, 'info');
        onSuccess?.();
      } catch (e) {
        console.error('Snapshot failed:', e);
        showToast?.(t.snapshotFailed, 'error');
        onError?.(e as Error);
      }
    } else {
      console.error('Snapshot action not bound');
    }
  }, [onSuccess, onError, showToast, t]);

  return {
    snapshotActionRef,
    handleSnapshot,
  };
}
