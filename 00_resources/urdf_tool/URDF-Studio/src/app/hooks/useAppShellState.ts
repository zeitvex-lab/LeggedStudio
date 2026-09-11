import { useCallback, useEffect, useRef, useState } from 'react';

import type { ExportProgressState } from '@/features/file-io';

export interface AppToastState {
  show: boolean;
  message: string;
  type: 'info' | 'success' | 'error';
}

export interface AppViewConfig {
  showOptionsPanel: boolean;
  showJointPanel: boolean;
  showStructureGraph: boolean;
}

export type AILaunchMode = 'inspection' | 'conversation' | null;

const DEFAULT_TOAST_STATE: AppToastState = {
  show: false,
  message: '',
  type: 'info',
};

const DEFAULT_VIEW_CONFIG: AppViewConfig = {
  showOptionsPanel: true,
  showJointPanel: true,
  showStructureGraph: false,
};

export function useAppShellState() {
  const [toast, setToast] = useState<AppToastState>(DEFAULT_TOAST_STATE);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isAIInspectionOpen, setIsAIInspectionOpen] = useState(false);
  const [isAIConversationOpen, setIsAIConversationOpen] = useState(false);
  const [aiLaunchMode, setAILaunchMode] = useState<AILaunchMode>(null);
  const [isCodeViewerOpen, setIsCodeViewerOpen] = useState(false);
  const [isExportDialogOpen, setIsExportDialogOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [projectExportProgress, setProjectExportProgress] = useState<ExportProgressState | null>(
    null,
  );
  const [viewConfig, setViewConfig] = useState<AppViewConfig>(DEFAULT_VIEW_CONFIG);

  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string, type: 'info' | 'success' | 'error' = 'info') => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }

    setToast({ show: true, message, type });
    toastTimerRef.current = setTimeout(() => {
      setToast((prev) => ({ ...prev, show: false }));
    }, 5000);
  }, []);

  const closeToast = useCallback(() => {
    setToast((prev) => ({ ...prev, show: false }));
  }, []);

  const openAIInspection = useCallback(() => {
    setIsAIInspectionOpen(true);
    setIsAIConversationOpen(false);
    setAILaunchMode('inspection');
  }, []);

  const openAIConversation = useCallback(() => {
    setIsAIConversationOpen(true);
    setIsAIInspectionOpen(false);
    setAILaunchMode('conversation');
  }, []);

  const closeAIEntryPoints = useCallback(() => {
    setIsAIInspectionOpen(false);
    setIsAIConversationOpen(false);
    setAILaunchMode(null);
  }, []);

  const isAIModalOpen = isAIInspectionOpen || isAIConversationOpen;

  const setIsAIModalOpen = useCallback(
    (open: boolean) => {
      if (open) {
        openAIInspection();
        return;
      }

      closeAIEntryPoints();
    },
    [closeAIEntryPoints, openAIInspection],
  );

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  return {
    toast,
    setToast,
    closeToast,
    showToast,
    isAboutOpen,
    setIsAboutOpen,
    isAIInspectionOpen,
    setIsAIInspectionOpen,
    isAIConversationOpen,
    setIsAIConversationOpen,
    aiLaunchMode,
    setAILaunchMode,
    openAIInspection,
    openAIConversation,
    closeAIEntryPoints,
    isAIModalOpen,
    setIsAIModalOpen,
    isCodeViewerOpen,
    setIsCodeViewerOpen,
    isExportDialogOpen,
    setIsExportDialogOpen,
    isExporting,
    setIsExporting,
    projectExportProgress,
    setProjectExportProgress,
    viewConfig,
    setViewConfig,
  };
}
