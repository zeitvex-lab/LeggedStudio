import type { AssemblyState, BridgeJoint } from '@/types';

/**
 * Build the read-only scene workspace used while authoring a bridge. The
 * canonical workspace object is returned unchanged when no complete preview
 * exists; otherwise only a structured clone receives the transient bridge.
 */
export function buildBridgePreviewWorkspace(
  workspace: AssemblyState,
  bridgePreview: BridgeJoint | null,
): AssemblyState {
  if (!bridgePreview) {
    return workspace;
  }

  const parentComponent = workspace.components[bridgePreview.parentComponentId];
  const childComponent = workspace.components[bridgePreview.childComponentId];
  if (
    !parentComponent ||
    !childComponent ||
    !parentComponent.visible ||
    !childComponent.visible ||
    !parentComponent.robot.links[bridgePreview.parentLinkId] ||
    !childComponent.robot.links[bridgePreview.childLinkId]
  ) {
    return workspace;
  }

  const previewWorkspace = structuredClone(workspace);
  previewWorkspace.bridges[bridgePreview.id] = structuredClone(bridgePreview);
  return previewWorkspace;
}
