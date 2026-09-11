import { useCallback } from 'react';

import type {
  LibraryRobotLoadIntent,
  LibraryRobotLoadResult,
} from '@/features/robot-tree';
import type { RobotFile } from '@/types';
import type { AppLayoutProps } from '../appLayoutTypes';
import { resolveLibraryRobotLoadAction } from '../utils/libraryRobotLoadPolicy';

interface UseLibraryRobotLoadRequestOptions {
  handlePreviewFileWithFeedback: (file: RobotFile) => void;
  hasSimpleModeSourceEdits: boolean;
  onLoadRobot: AppLayoutProps['onLoadRobot'];
  selectedFile: RobotFile | null;
  shouldPreviewLibraryRobotLoad: boolean;
}

export function useLibraryRobotLoadRequest({
  handlePreviewFileWithFeedback,
  hasSimpleModeSourceEdits,
  onLoadRobot,
  selectedFile,
  shouldPreviewLibraryRobotLoad,
}: UseLibraryRobotLoadRequestOptions) {
  return useCallback(
    async (
      file: RobotFile,
      intent: LibraryRobotLoadIntent,
    ): Promise<LibraryRobotLoadResult> => {
      const loadAction = resolveLibraryRobotLoadAction({
        selectedFileName: selectedFile?.name,
        shouldPreviewCurrentState: shouldPreviewLibraryRobotLoad,
        hasSimpleModeSourceEdits,
        intent,
      });

      if (loadAction === 'preview') {
        handlePreviewFileWithFeedback(file);
        return 'loaded';
      }

      if (loadAction === 'load') {
        const outcome = await onLoadRobot(file);
        return outcome ? 'loaded' : 'blocked';
      }

      if (loadAction === 'needs-preview-or-discard-confirm') {
        return 'needs-preview-or-discard-confirm';
      }

      return 'blocked';
    },
    [
      handlePreviewFileWithFeedback,
      hasSimpleModeSourceEdits,
      onLoadRobot,
      selectedFile,
      shouldPreviewLibraryRobotLoad,
    ],
  );
}
