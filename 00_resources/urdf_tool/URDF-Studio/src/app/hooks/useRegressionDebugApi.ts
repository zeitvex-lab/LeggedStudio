import { useEffect, type MutableRefObject } from 'react';
import {
  useAssetsStore,
  useSelectionStore,
  useUIStore,
} from '@/store';
import { useJointPickSessionStore } from '@/store/jointPickSessionStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { projectWorkspaceSelectionToRenderer } from '@/features/editor';
import type { InteractionSelection, RobotFile, WorkspaceSelection } from '@/types';
import { setRegressionBeforeUnloadPromptSuppressed } from '@/shared/debug/regressionPromptSuppression';
import {
  clearRegressionDebugGlobals,
  isRegressionDebugEnabled,
} from '@/shared/debug/regressionDebugEnabled';
import type {
  CommitResolvedRobotLoadOutcome,
  WorkspaceLoadIntent,
} from '@/app/utils/commitResolvedRobotLoad';

type LoadRobotByNameRef = MutableRefObject<
  | ((
      file: RobotFile,
      options?: { forceReload?: boolean; intent?: WorkspaceLoadIntent },
    ) => Promise<CommitResolvedRobotLoadOutcome | null> | CommitResolvedRobotLoadOutcome | null)
  | null
>;

function projectDebugSelection(selection: WorkspaceSelection): InteractionSelection {
  const projection = useWorkspaceStore.getState().getSceneProjection();
  return projectWorkspaceSelectionToRenderer(projection, selection);
}

export function useRegressionDebugApi(loadRobotByNameRef: LoadRobotByNameRef): void {
  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    if (!isRegressionDebugEnabled(window)) {
      return;
    }

    let disposed = false;
    let clearRegressionAppHandlers: (() => void) | null = null;

    void import('@/shared/debug/regressionBridge').then(
      ({ installRegressionDebugApi, setRegressionAppHandlers }) => {
        if (disposed) {
          return;
        }

        installRegressionDebugApi(window);
        const regressionApi = window.__URDF_STUDIO_DEBUG__ as typeof window.__URDF_STUDIO_DEBUG__ & {
          __workspaceStore__?: typeof useWorkspaceStore;
          __uiStore__?: typeof useUIStore;
          __assetsStore__?: typeof useAssetsStore;
          __selectionStore__?: typeof useSelectionStore;
          __jointPickSessionStore__?: typeof useJointPickSessionStore;
        };
        regressionApi.__workspaceStore__ = useWorkspaceStore;
        regressionApi.__uiStore__ = useUIStore;
        regressionApi.__assetsStore__ = useAssetsStore;
        regressionApi.__selectionStore__ = useSelectionStore;
        regressionApi.__jointPickSessionStore__ = useJointPickSessionStore;

        setRegressionAppHandlers({
          getAvailableFiles: () => useAssetsStore.getState().availableFiles,
          getSelectedFile: () => useAssetsStore.getState().selectedFile,
          getUsdSceneSnapshot: (fileName: string) =>
            useAssetsStore.getState().getUsdSceneSnapshot(fileName),
          getDocumentLoadState: () => useAssetsStore.getState().documentLoadState,
          getRobotState: () => {
            const projection = useWorkspaceStore.getState().getSceneProjection();
            return {
              ...projection.robotData,
              selection: projectDebugSelection(useSelectionStore.getState().selection),
            };
          },
          getAssetDebugState: () => {
            const assetsState = useAssetsStore.getState();
            return {
              appAssetKeys: Object.keys(assetsState.assets).sort((left, right) =>
                left.localeCompare(right),
              ),
              preparedUsdCacheKeysByFile: Object.fromEntries(
                Object.entries(assetsState.usdPreparedExportCaches)
                  .sort(([left], [right]) => left.localeCompare(right))
                  .map(([fileName, cache]) => [
                    fileName,
                    Object.keys(cache.meshFiles || {}).sort((left, right) =>
                      left.localeCompare(right),
                    ),
                  ]),
              ),
            };
          },
          getInteractionState: () => ({
            selection: projectDebugSelection(useSelectionStore.getState().selection),
            hoveredSelection: projectDebugSelection(
              useSelectionStore.getState().hoveredSelection,
            ),
          }),
          resetFixtureFiles: () => {
            const assetsState = useAssetsStore.getState();
            assetsState.revokeAllAssets();
            assetsState.setAssets({});
            assetsState.setAvailableFiles([]);
            assetsState.setAllFileContents({});
            assetsState.clearUsdSceneSnapshots();
            assetsState.clearUsdPreparedExportCaches();
            assetsState.setSelectedFile(null);
            assetsState.resetDocumentLoadState();
          },
          seedFixtureFile: (file) => {
            const assetsState = useAssetsStore.getState();
            const normalizedName = file.name.replace(/\\/g, '/').replace(/^\/+/, '');
            const nextFile = {
              name: normalizedName,
              content: file.content,
              format: file.format,
              ...(file.blobUrl ? { blobUrl: file.blobUrl } : {}),
            };

            if (file.blobUrl) {
              assetsState.addAsset(normalizedName, file.blobUrl);
            }
            assetsState.addRobotFile(nextFile);
            if (file.addFileContent) {
              assetsState.addFileContent(normalizedName, file.content);
            }

            return {
              availableFileCount: useAssetsStore.getState().availableFiles.length,
            };
          },
          loadRobotByName: async (fileName: string) => {
            const file =
              useAssetsStore.getState().availableFiles.find((entry) => entry.name === fileName) ??
              null;
            if (!file) {
              return {
                loaded: false,
                selectedFile: useAssetsStore.getState().selectedFile?.name ?? null,
              };
            }

            loadRobotByNameRef.current?.(file, { forceReload: true });
            return {
              loaded: true,
              selectedFile: file.name,
            };
          },
        });

        clearRegressionAppHandlers = () => {
          setRegressionAppHandlers(null);
        };
      },
    );

    return () => {
      disposed = true;
      clearRegressionAppHandlers?.();
      setRegressionBeforeUnloadPromptSuppressed(false);
      clearRegressionDebugGlobals(window);
    };
  }, [loadRobotByNameRef]);
}
