export interface WorkspaceOverlayLayoutClassNames {
  root: string;
  viewerLayer: string;
  leftSidebarLayer: string;
  rightSidebarLayer: string;
}

export function resolveWorkspaceOverlayLayoutClassNames(): WorkspaceOverlayLayoutClassNames {
  return {
    root: 'flex-1 relative overflow-hidden',
    viewerLayer: 'absolute inset-0 z-0 min-w-0 overflow-hidden',
    leftSidebarLayer: 'absolute inset-y-0 left-0 z-20 h-full w-auto',
    rightSidebarLayer: 'pointer-events-none absolute inset-y-0 right-0 z-20 h-full w-auto',
  };
}
