import { useMemo } from 'react';
import {
  resolveWorkspaceOverlayGizmoMargin,
  resolveWorkspaceOverlaySafeAreaStyle,
  type WorkspaceOverlayGizmoMargin,
} from '@/shared/components/3d/scene/viewerOverlaySafeArea';
import { resolveWorkspaceOverlayLayoutClassNames } from '../utils/workspaceOverlayLayout';

interface UseWorkspaceLayoutDerivationsParams {
  panelLayout: {
    propertyEditorWidth: number;
    treeSidebarWidth: number;
  };
  sidebar: {
    leftCollapsed: boolean;
    rightCollapsed: boolean;
  };
}

export function useWorkspaceLayoutDerivations({
  panelLayout,
  sidebar,
}: UseWorkspaceLayoutDerivationsParams) {
  const workspaceLayoutClassNames = useMemo(() => resolveWorkspaceOverlayLayoutClassNames(), []);
  const workspaceOverlaySafeAreaStyle = useMemo(
    () =>
      resolveWorkspaceOverlaySafeAreaStyle({
        leftCollapsed: sidebar.leftCollapsed,
        propertyEditorWidth: panelLayout.propertyEditorWidth,
        rightCollapsed: sidebar.rightCollapsed,
        treeSidebarWidth: panelLayout.treeSidebarWidth,
      }),
    [
      panelLayout.propertyEditorWidth,
      panelLayout.treeSidebarWidth,
      sidebar.leftCollapsed,
      sidebar.rightCollapsed,
    ],
  );
  const workspaceOverlayGizmoMargin = useMemo<WorkspaceOverlayGizmoMargin>(
    () =>
      resolveWorkspaceOverlayGizmoMargin({
        leftCollapsed: sidebar.leftCollapsed,
        propertyEditorWidth: panelLayout.propertyEditorWidth,
        rightCollapsed: sidebar.rightCollapsed,
        treeSidebarWidth: panelLayout.treeSidebarWidth,
      }),
    [
      panelLayout.propertyEditorWidth,
      panelLayout.treeSidebarWidth,
      sidebar.leftCollapsed,
      sidebar.rightCollapsed,
    ],
  );

  return {
    workspaceLayoutClassNames,
    workspaceOverlaySafeAreaStyle,
    workspaceOverlayGizmoMargin,
  };
}
