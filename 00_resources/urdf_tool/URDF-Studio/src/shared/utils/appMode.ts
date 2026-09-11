import type { AppMode } from '@/types';

export const MERGED_EDIT_APP_MODE: AppMode = 'editor';

/**
 * The workspace exposes a single editor mode.
 */
export function normalizeMergedAppMode(mode: AppMode): AppMode {
  return mode;
}
