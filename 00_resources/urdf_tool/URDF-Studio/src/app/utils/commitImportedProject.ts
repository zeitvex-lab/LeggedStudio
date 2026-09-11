import type { ProjectImportResult } from '@/features/file-io';
import { useAssetsStore } from '@/store/assetsStore';
import {
  repairWorkspaceSelection,
  useSelectionStore,
} from '@/store/selectionStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { RobotFile } from '@/types';

import {
  cancelPendingUsdWorkspaceLoad,
  getPendingUsdWorkspaceLoad,
} from './commitResolvedRobotLoad';
import { revokeBlobUrls } from '../hooks/import_blob_urls';

export interface CommitImportedProjectOptions {
  markWorkspaceBaselineSaved?: () => void;
}

function cancelCurrentWorkspaceOperation(): void {
  const pendingUsd = getPendingUsdWorkspaceLoad();
  if (pendingUsd) {
    cancelPendingUsdWorkspaceLoad(pendingUsd.operationId);
  }
  const transactionId = useWorkspaceStore.getState().transaction?.id;
  if (transactionId) {
    useWorkspaceStore.getState().cancelWorkspaceTransaction(transactionId);
  }
}

function revokeReplacedAssetUrls(
  previousAssets: Record<string, string>,
  nextAssets: Record<string, string>,
): void {
  const retainedUrls = new Set(Object.values(nextAssets));
  revokeBlobUrls(
    Object.values(previousAssets).filter((url) => !retainedUrls.has(url)),
  );
}

/** Commit an already fully validated/hydrated USP result without partial store writes. */
export function commitImportedProject(
  result: ProjectImportResult,
  options: CommitImportedProjectOptions = {},
): RobotFile | null {
  cancelCurrentWorkspaceOperation();
  const workspaceStore = useWorkspaceStore.getState();
  const previousWorkspace = structuredClone(workspaceStore.workspace);
  const previousHistory = structuredClone(workspaceStore.history);
  const previousActiveComponentId = workspaceStore.activeComponentId;
  const previousSelection = useSelectionStore.getState().selection;
  const assetsStoreBefore = useAssetsStore.getState();
  const previousAssetsState = {
    assets: assetsStoreBefore.assets,
    availableFiles: assetsStoreBefore.availableFiles,
    allFileContents: assetsStoreBefore.allFileContents,
    motorLibrary: assetsStoreBefore.motorLibrary,
    selectedFile: assetsStoreBefore.selectedFile,
    usdSceneSnapshots: assetsStoreBefore.usdSceneSnapshots,
    usdPreparedExportCaches: assetsStoreBefore.usdPreparedExportCaches,
    componentSourceDrafts: assetsStoreBefore.componentSourceDrafts,
    documentLoadState: assetsStoreBefore.documentLoadState,
  };
  const provisionalUrls = Object.values(result.assets.assetUrls);
  let workspaceRestored = false;

  try {
    if (!workspaceStore.restoreWorkspace(result.workspace, result.workspaceHistory)) {
      throw new Error('Workspace rejected the imported project snapshot.');
    }
    workspaceRestored = true;
    const restoredWorkspaceState = useWorkspaceStore.getState();
    const restoredSelectedFile = result.assets.selectedFileName
      ? result.assets.availableFiles.find(
          (file) => file.name === result.assets.selectedFileName,
        ) ?? null
      : null;
    useAssetsStore.setState({
      assets: result.assets.assetUrls,
      availableFiles: result.assets.availableFiles,
      allFileContents: result.assets.allFileContents,
      motorLibrary: result.assets.motorLibrary,
      selectedFile: restoredSelectedFile,
      usdSceneSnapshots: {},
      usdPreparedExportCaches:
        result.derivedCaches.usdPreparedExportCaches,
      componentSourceDrafts: result.componentSourceDrafts,
      documentLoadState: restoredSelectedFile
        ? {
            status: 'ready',
            fileName: restoredSelectedFile.name,
            format: restoredSelectedFile.format,
            error: null,
            phase: 'ready',
            progressMode: 'percent',
            progressPercent: 100,
          }
        : { status: 'idle', fileName: null, format: null, error: null },
    });
    useSelectionStore.getState().setSelection(
      repairWorkspaceSelection(
        restoredWorkspaceState.workspace,
        previousSelection,
        restoredWorkspaceState.activeComponentId,
      ),
    );
    options.markWorkspaceBaselineSaved?.();
    revokeReplacedAssetUrls(previousAssetsState.assets, result.assets.assetUrls);
    return restoredSelectedFile;
  } catch (error) {
    const currentWorkspaceStore = useWorkspaceStore.getState();
    if (workspaceRestored && !currentWorkspaceStore.transaction) {
      currentWorkspaceStore.restoreWorkspace(previousWorkspace, previousHistory);
      useWorkspaceStore.setState({ activeComponentId: previousActiveComponentId });
    }
    useAssetsStore.setState(previousAssetsState);
    useSelectionStore.setState({ selection: previousSelection });
    revokeBlobUrls(provisionalUrls);
    throw error;
  }
}
