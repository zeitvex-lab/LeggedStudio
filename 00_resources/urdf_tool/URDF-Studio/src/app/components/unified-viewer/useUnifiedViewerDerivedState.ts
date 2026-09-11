import React from 'react';

import type { AppMode, RobotData, RobotFile, Theme } from '@/types';
import { useResolvedTheme } from '@/shared/hooks/useTheme';
import {
  createInitialUnifiedViewerMountState,
  resolveUnifiedViewerMountState,
  resolveUnifiedViewerSessionState,
  type UnifiedViewerMountState,
} from '@/app/utils/unifiedViewerMountState';
import { captureUnifiedViewerOptionsVisibility } from '@/app/utils/unifiedViewerOptionsRestore';
import { buildUnifiedViewerResourceScopes } from '@/app/utils/unifiedViewerResourceScopes';
import { resolveUnifiedViewerViewportState } from '@/app/utils/unifiedViewerViewportState';
import { useUIStore } from '@/store';
import type { DocumentLoadLifecycleState } from '@/store/assetsStore';
import { setRegressionViewerResourceScope } from '@/shared/debug/regressionState';
import {
  buildViewerRobotLinksScopeSignature,
  type ViewerResourceScope,
} from '@/features/editor';
import type { ToolMode } from '@/features/editor';

import type { FilePreviewState } from './types';

interface UseUnifiedViewerDerivedStateParams {
  mode: AppMode;
  filePreview?: FilePreviewState;
  pendingViewerToolMode?: ToolMode | null;
  theme: Theme;
  showOptionsPanel: boolean;
  // Viewer-bound robot is RobotData (no selection) — keeping it selection-free
  // is what stops the empty-click cascade that flashes models off for a frame.
  robot: RobotData;
  urdfContent: string;
  sourceFilePath?: string;
  sourceFile?: RobotFile | null;
  assets: Record<string, string>;
  allFileContents: Record<string, string>;
  availableFiles: RobotFile[];
  viewerReloadKey?: number;
  documentLoadState: DocumentLoadLifecycleState;
}

export function useUnifiedViewerDerivedState({
  mode,
  filePreview,
  pendingViewerToolMode = null,
  theme,
  showOptionsPanel,
  robot,
  urdfContent,
  sourceFilePath,
  sourceFile,
  assets,
  allFileContents,
  availableFiles,
  viewerReloadKey = 0,
  documentLoadState,
}: UseUnifiedViewerDerivedStateParams) {
  const groundPlaneOffset = useUIStore((state) => state.groundPlaneOffset);
  const setGroundPlaneOffset = useUIStore((state) => state.setGroundPlaneOffset);
  const [forcedViewerSession, setForcedViewerSession] = React.useState(false);
  const viewerToolSessionActive = pendingViewerToolMode === 'measure' || forcedViewerSession;
  const sessionState = React.useMemo(
    () =>
      resolveUnifiedViewerSessionState({
        mode,
        filePreview,
        forceViewerSession: viewerToolSessionActive,
      }),
    [filePreview, mode, viewerToolSessionActive],
  );
  const { activePreview, isPreviewing, isViewerMode } = sessionState;
  const viewerSceneMode = sessionState.viewerSceneMode;
  const [mountState, setMountState] = React.useState<UnifiedViewerMountState>(() =>
    createInitialUnifiedViewerMountState({
      mode,
      isPreviewing,
      forceViewerSession: viewerToolSessionActive,
    }),
  );
  const resolvedTheme = useResolvedTheme(theme);
  const viewerOptionsVisibleRef = React.useRef(showOptionsPanel);
  const viewerResourceScopeRef = React.useRef<ViewerResourceScope | null>(null);
  const optionsVisibleAtPointerDownRef = React.useRef(
    captureUnifiedViewerOptionsVisibility({
      showViewerOptions: showOptionsPanel,
    }),
  );

  React.useEffect(() => {
    viewerOptionsVisibleRef.current = showOptionsPanel;
  }, [showOptionsPanel]);

  React.useEffect(() => {
    setMountState((current) =>
      resolveUnifiedViewerMountState(current, {
        mode,
        isPreviewing,
        forceViewerSession: viewerToolSessionActive,
      }),
    );
  }, [isPreviewing, mode, viewerToolSessionActive]);

  const viewerRobotLinksScopeSignature = React.useMemo(
    () =>
      buildViewerRobotLinksScopeSignature(
        activePreview ? undefined : robot.links,
        activePreview ? undefined : robot.materials,
      ),
    [activePreview, robot.links, robot.materials],
  );
  const viewerRobotLinksForScope = React.useMemo(
    () => (activePreview ? undefined : robot.links),
    [activePreview, viewerRobotLinksScopeSignature],
  );
  const viewerRobotMaterialsForScope = React.useMemo(
    () => (activePreview ? undefined : robot.materials),
    [activePreview, viewerRobotLinksScopeSignature],
  );
  const {
    effectiveUrdfContent,
    effectiveSourceFilePath,
    effectiveSourceFile,
    activeViewportFileName,
    viewerResourceScope,
  } = React.useMemo(() => {
    const next = buildUnifiedViewerResourceScopes({
      activePreview,
      urdfContent,
      sourceFilePath,
      sourceFile,
      assets,
      allFileContents,
      availableFiles,
      viewerRobotLinks: viewerRobotLinksForScope,
      viewerRobotMaterials: viewerRobotMaterialsForScope,
      previousViewerResourceScope: viewerResourceScopeRef.current,
    });
    viewerResourceScopeRef.current = next.viewerResourceScope;
    return next;
  }, [
    activePreview,
    assets,
    allFileContents,
    availableFiles,
    sourceFile,
    sourceFilePath,
    urdfContent,
    viewerRobotLinksForScope,
    viewerRobotMaterialsForScope,
  ]);

  React.useEffect(() => {
    setRegressionViewerResourceScope({
      sourceFileName: effectiveSourceFile?.name ?? null,
      sourceFilePath: effectiveSourceFilePath ?? null,
      assetKeys: Object.keys(viewerResourceScope.assets).sort((left, right) =>
        left.localeCompare(right),
      ),
      availableFileNames: viewerResourceScope.availableFiles
        .map((file) => file.name)
        .sort((left, right) => left.localeCompare(right)),
      signature: viewerResourceScope.signature,
    });

    return () => {
      setRegressionViewerResourceScope(null);
    };
  }, [effectiveSourceFile?.name, effectiveSourceFilePath, viewerResourceScope]);

  const viewportState = React.useMemo(
    () =>
      resolveUnifiedViewerViewportState({
        isViewerMode,
        mountState,
        activeViewportFileName,
        viewerReloadKey,
        documentLoadState,
      }),
    [activeViewportFileName, documentLoadState, isViewerMode, mountState, viewerReloadKey],
  );

  return {
    groundPlaneOffset,
    setGroundPlaneOffset,
    forcedViewerSession,
    setForcedViewerSession,
    activePreview,
    isPreviewing,
    isViewerMode,
    viewerSceneMode,
    mountState,
    setMountState,
    resolvedTheme,
    viewerOptionsVisibleRef,
    optionsVisibleAtPointerDownRef,
    effectiveUrdfContent,
    effectiveSourceFilePath,
    effectiveSourceFile,
    activeViewportFileName,
    viewerResourceScope,
    viewportState,
  };
}
