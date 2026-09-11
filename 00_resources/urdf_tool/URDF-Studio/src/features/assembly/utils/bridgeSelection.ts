import type {
  AssemblyComponent,
  AssemblyState,
  WorkspaceSelection,
} from '@/types';
import type { BridgePickTarget } from '@/shared/utils/assembly/bridgePickAssignment';

export type { BridgePickTarget };
export { resolveBridgePickAssignment } from '@/shared/utils/assembly/bridgePickAssignment';

export interface ResolvedBridgeSelectionTarget {
  componentId: string;
  componentName: string;
  linkId: string;
  linkName: string;
}

export interface BridgeInteractionState {
  pickTarget: BridgePickTarget;
  parentComponentId: string;
  childComponentId: string;
}

/**
 * Resolve a canonical workspace pick to the link used by a bridge endpoint.
 * Ownership always comes from EntityRef; source-local IDs are never scanned
 * across components or reconstructed from renderer prefixes.
 */
export function resolveBridgeSelectionTarget(
  workspace: AssemblyState,
  selection: WorkspaceSelection,
): ResolvedBridgeSelectionTarget | null {
  if (!selection) {
    return null;
  }

  const ref = selection.entity;
  if (ref.type !== 'link' && ref.type !== 'joint') {
    return null;
  }

  const component = workspace.components[ref.componentId];
  if (!component) {
    return null;
  }

  const linkId = ref.type === 'link'
    ? ref.entityId
    : component.robot.joints[ref.entityId]?.childLinkId;
  if (!linkId) {
    return null;
  }

  const link = component.robot.links[linkId];
  if (!link) {
    return null;
  }

  return {
    componentId: component.id,
    componentName: component.name,
    linkId: link.id,
    linkName: link.name,
  };
}

export function resolveBlockedBridgeComponentId({
  pickTarget,
  parentComponentId,
  childComponentId,
}: BridgeInteractionState): string | null {
  if (pickTarget === 'parent') {
    return childComponentId || null;
  }

  return parentComponentId || null;
}

export function isWorkspaceSelectionAllowedForBridge(
  workspace: AssemblyState,
  selection: WorkspaceSelection,
  blockedComponentId: string | null,
): boolean {
  if (!selection || !blockedComponentId) {
    return true;
  }

  const resolvedSelection = resolveBridgeSelectionTarget(workspace, selection);
  return Boolean(
    resolvedSelection && resolvedSelection.componentId !== blockedComponentId,
  );
}

export function filterSelectableBridgeComponents(
  components: AssemblyComponent[],
  blockedComponentId: string | null,
): AssemblyComponent[] {
  if (!blockedComponentId) {
    return components;
  }

  return components.filter((component) => component.id !== blockedComponentId);
}
