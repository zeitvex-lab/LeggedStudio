import {
  resolveWorkspaceRobotDataTarget,
  type WorkspaceInspectableEntityRef,
  type WorkspaceRobotDataTarget,
} from '@/core/robot';
import type { AssemblyState, WorkspaceSelection } from '@/types';

import type { AIConversationSelection } from '../types';

export type AIInspectableEntityRef = WorkspaceInspectableEntityRef;

export interface AIWorkspaceRobotTarget extends WorkspaceRobotDataTarget {
  selectedEntity: AIConversationSelection | null;
}

function getSelectedInspectableEntity(
  selection: WorkspaceSelection,
): AIInspectableEntityRef | null {
  const ref = selection?.entity;
  return ref?.type === 'link' || ref?.type === 'joint' ? ref : null;
}

/** Attach canonical conversation identity to the selected immutable robot view. */
export function resolveAIWorkspaceRobotTarget(
  workspace: AssemblyState,
  selection: WorkspaceSelection,
): AIWorkspaceRobotTarget {
  const target = resolveWorkspaceRobotDataTarget(workspace, selection);
  const selectedRef = getSelectedInspectableEntity(selection);
  const selectedEntity = selectedRef && target.componentId === selectedRef.componentId
    ? { ...selectedRef, snapshotEntityId: selectedRef.entityId }
    : null;

  return { ...target, selectedEntity };
}
