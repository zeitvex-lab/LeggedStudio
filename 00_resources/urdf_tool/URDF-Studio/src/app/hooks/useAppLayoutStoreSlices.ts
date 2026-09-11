import { useMemo } from 'react';
import { useShallow } from 'zustand/react/shallow';

import {
  useAssetsStore,
  useCollisionTransformStore,
  useSelectionStore,
  useUIStore,
} from '@/store';
import { toDocumentLoadLifecycleState } from '@/store/assetsStore';
import { useWorkspaceStore } from '@/store/workspaceStore';

type WorkspaceStoreState = ReturnType<typeof useWorkspaceStore.getState>;

export function createSemanticWorkspaceSelector() {
  let cachedRevision: number | null = null;
  let cachedWorkspace: WorkspaceStoreState['workspace'] | null = null;
  return (state: WorkspaceStoreState) => {
    const semanticRevision = state.revision - state.jointMotionRevision;
    if (cachedRevision !== semanticRevision || !cachedWorkspace) {
      cachedRevision = semanticRevision;
      cachedWorkspace = state.workspace;
    }
    return cachedWorkspace;
  };
}

export function useAppLayoutStoreSlices() {
  const uiStore = useUIStore(
    useShallow((state) => ({
      appMode: state.appMode,
      lang: state.lang,
      theme: state.theme,
      sidebar: state.sidebar,
      panelLayout: state.panelLayout,
      toggleSidebar: state.toggleSidebar,
      setSidebar: state.setSidebar,
      sourceCodeAutoApply: state.sourceCodeAutoApply,
      setViewOption: state.setViewOption,
      groundPlaneOffset: state.groundPlaneOffset,
    })),
  );

  const selectionStore = useSelectionStore(
    useShallow((state) => ({
      selection: state.selection,
      setSelection: state.setSelection,
      setHoveredSelection: state.setHoveredSelection,
      clearSelection: state.clearSelection,
      selectComponent: state.selectComponent,
      focusTarget: state.focusTarget,
      focusOn: state.focusOn,
      pulseSelection: state.pulseSelection,
    })),
  );

  const assetsStore = useAssetsStore(
    useShallow((state) => ({
      assets: state.assets,
      motorLibrary: state.motorLibrary,
      availableFiles: state.availableFiles,
      selectedFile: state.selectedFile,
      documentLoadState: state.documentLoadState,
      allFileContents: state.allFileContents,
      setAvailableFiles: state.setAvailableFiles,
      setSelectedFile: state.setSelectedFile,
      setAllFileContents: state.setAllFileContents,
      componentSourceDrafts: state.componentSourceDrafts,
      setComponentSourceDraft: state.setComponentSourceDraft,
      removeComponentSourceDraft: state.removeComponentSourceDraft,
      clearComponentSourceDrafts: state.clearComponentSourceDrafts,
      uploadAsset: state.uploadAsset,
      removeRobotFile: state.removeRobotFile,
      removeRobotFolder: state.removeRobotFolder,
      renameRobotFolder: state.renameRobotFolder,
      clearRobotLibrary: state.clearRobotLibrary,
      getUsdPreparedExportCache: state.getUsdPreparedExportCache,
      usdPreparedExportCaches: state.usdPreparedExportCaches,
      setDocumentLoadState: state.setDocumentLoadState,
    })),
  );
  const documentLoadLifecycleState = useMemo(
    () => toDocumentLoadLifecycleState(assetsStore.documentLoadState),
    [assetsStore.documentLoadState],
  );

  const semanticWorkspaceSelector = useMemo(createSemanticWorkspaceSelector, []);
  const semanticWorkspace = useWorkspaceStore(semanticWorkspaceSelector);
  const workspaceStore = useWorkspaceStore(
    useShallow((state) => ({
      workspace: state.workspace,
      activeComponentId: state.activeComponentId,
      transaction: state.transaction,
      replaceWorkspace: state.replaceWorkspace,
      resetWorkspace: state.resetWorkspace,
      renameWorkspace: state.renameWorkspace,
      setActiveComponent: state.setActiveComponent,
      appendComponent: state.appendComponent,
      insertComponent: state.insertComponent,
      removeComponent: state.removeComponent,
      renameComponent: state.renameComponent,
      updateComponentTransform: state.updateComponentTransform,
      setComponentVisibility: state.setComponentVisibility,
      replaceComponentRobot: state.replaceComponentRobot,
      addChild: state.addChild,
      deleteSubtree: state.deleteSubtree,
      updateLink: state.updateLink,
      updateJoint: state.updateJoint,
      updateTendon: state.updateTendon,
      setAllLinksVisibility: state.setAllLinksVisibility,
      setJointMotion: state.setJointMotion,
      setComponentJointMotion: state.setComponentJointMotion,
      flushPendingJointMotion: state.flushPendingJointMotion,
      addBridge: state.addBridge,
      removeBridge: state.removeBridge,
      updateBridge: state.updateBridge,
      updateAssemblyTransform: state.updateAssemblyTransform,
    })),
  );

  const collisionTransformStore = useCollisionTransformStore(
    useShallow((state) => ({
      setPendingCollisionTransform: state.setPendingCollisionTransform,
      clearPendingCollisionTransform: state.clearPendingCollisionTransform,
    })),
  );

  return {
    uiStore,
    selectionStore,
    assetsStore: {
      ...assetsStore,
      documentLoadLifecycleState,
    },
    workspaceStore: {
      ...workspaceStore,
      semanticWorkspace,
    },
    collisionTransformStore,
  };
}
