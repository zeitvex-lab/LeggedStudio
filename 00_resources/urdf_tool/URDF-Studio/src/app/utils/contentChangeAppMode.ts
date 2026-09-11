import type { AppMode } from '@/types';
import { normalizeMergedAppMode } from '@/shared/utils/appMode';

/**
 * Newly loaded robot content should reopen in editor mode.
 */
export function resolveAppModeAfterRobotContentChange(mode: AppMode): AppMode {
  return normalizeMergedAppMode(mode);
}
