import React from 'react';

const loadViewerSceneConnectorModule = () => import('./ViewerSceneConnector');
const loadViewerPanelsModule = () => import('@/features/editor/panels');
const loadViewerJointsPanelModule = () => import('./ViewerJointsPanel');

export const LazyViewerSceneConnector = React.lazy(async () => ({
  default: (await loadViewerSceneConnectorModule()).ViewerSceneConnector,
}));

export const LazyViewerPanels = React.lazy(async () => ({
  default: (await loadViewerPanelsModule()).ViewerPanels,
}));

export const LazyViewerJointsPanel = React.lazy(async () => ({
  default: (await loadViewerJointsPanelModule()).ViewerJointsPanel,
}));

export async function preloadDeferredViewerModeModules(): Promise<void> {
  await loadViewerJointsPanelModule();
}
