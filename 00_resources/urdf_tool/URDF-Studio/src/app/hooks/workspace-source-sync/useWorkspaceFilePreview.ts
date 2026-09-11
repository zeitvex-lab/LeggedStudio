import { useCallback, useEffect, useRef, useState } from 'react';
import { scheduleFailFastInDev } from '@/core/utils/runtimeDiagnostics';
import type { RobotData, RobotFile, RobotState } from '@/types';
import { resolveRobotFileDataWithWorker } from '../robotImportWorkerBridge';
import {
  buildPreviewSceneSourceFromImportResult,
  createPreviewRobotStateFromImportResult,
} from '../workspaceSourceSyncUtils';

interface UseWorkspaceFilePreviewParams {
  availableFiles: RobotFile[];
  assets: Record<string, string>;
  allFileContents: Record<string, string>;
  getUsdPreparedExportCache: (path: string) => { robotData?: RobotData } | null;
}

export interface WorkspaceFilePreviewState {
  filePreview: { urdfContent: string; fileName: string } | undefined;
  previewRobot: RobotState | null;
  previewFileName: string | undefined;
  handlePreviewFile: (file: RobotFile) => void;
  handleClosePreview: () => void;
  activePreviewFile: RobotFile | null;
}

export function useWorkspaceFilePreview({
  availableFiles,
  assets,
  allFileContents,
  getUsdPreparedExportCache,
}: UseWorkspaceFilePreviewParams): WorkspaceFilePreviewState {
  const [activePreviewFile, setActivePreviewFile] = useState<RobotFile | null>(null);
  const [previewRobot, setPreviewRobot] = useState<RobotState | null>(null);
  const [filePreview, setFilePreview] = useState<
    { urdfContent: string; fileName: string } | undefined
  >(undefined);
  const previewRequestRef = useRef(0);

  useEffect(() => {
    if (!activePreviewFile) {
      previewRequestRef.current += 1;
      setPreviewRobot(null);
      setFilePreview(undefined);
      return;
    }

    const requestId = ++previewRequestRef.current;
    setPreviewRobot(null);
    setFilePreview(undefined);

    void resolveRobotFileDataWithWorker(activePreviewFile, {
      availableFiles,
      assets,
      allFileContents,
      usdRobotData: getUsdPreparedExportCache(activePreviewFile.name)?.robotData ?? null,
    })
      .then((result) => {
        if (requestId !== previewRequestRef.current) {
          return;
        }

        const nextPreviewRobot = createPreviewRobotStateFromImportResult(activePreviewFile, result);
        const previewUrdf = buildPreviewSceneSourceFromImportResult(activePreviewFile, {
          availableFiles,
          previewRobot: nextPreviewRobot,
          importResult: result,
        });
        const shouldActivatePreview =
          previewUrdf != null &&
          (activePreviewFile.format === 'usd' || previewUrdf.trim().length > 0);

        if (!shouldActivatePreview) {
          setPreviewRobot(null);
          setFilePreview(undefined);
          return;
        }

        setPreviewRobot(nextPreviewRobot);
        setFilePreview({ urdfContent: previewUrdf, fileName: activePreviewFile.name });
      })
      .catch((error) => {
        if (requestId !== previewRequestRef.current) {
          return;
        }

        setPreviewRobot(null);
        setFilePreview(undefined);
        scheduleFailFastInDev(
          'useWorkspaceFilePreview:filePreview',
          new Error(`Failed to resolve file preview for "${activePreviewFile.name}".`, {
            cause: error,
          }),
        );
      });
  }, [activePreviewFile, allFileContents, assets, availableFiles, getUsdPreparedExportCache]);

  useEffect(() => {
    if (!activePreviewFile) {
      return;
    }

    const exists = availableFiles.some((file) => file.name === activePreviewFile.name);
    if (!exists) {
      setActivePreviewFile(null);
    }
  }, [activePreviewFile, availableFiles]);

  const handlePreviewFile = useCallback((file: RobotFile) => {
    setActivePreviewFile(file);
  }, []);

  const handleClosePreview = useCallback(() => {
    setActivePreviewFile(null);
  }, []);

  return {
    filePreview,
    previewRobot,
    previewFileName: activePreviewFile?.name,
    handlePreviewFile,
    handleClosePreview,
    activePreviewFile,
  };
}
