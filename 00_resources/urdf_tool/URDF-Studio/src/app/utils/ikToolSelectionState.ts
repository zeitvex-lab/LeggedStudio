import { resolveSelectedIkDragLinkId } from '@/features/editor/ik_selection';
import type { InteractionSelection, UrdfJoint, UrdfLink } from '@/types';

export type IkToolSelectionStatus =
  | 'idle'
  | 'selected'
  | 'root_not_draggable'
  | 'no_variable_chain';

interface ResolveIkToolSelectionStateOptions {
  selection: InteractionSelection | null | undefined;
  ikDragActive?: boolean;
  robotLinks?: Record<string, UrdfLink> | null;
  robotJoints?: Record<string, UrdfJoint> | null;
  rootLinkId?: string | null;
}

export interface IkToolSelectionState {
  status: IkToolSelectionStatus;
  currentLinkId: string | null;
  selectedLinkId: string | null;
}

export function resolveIkToolSelectionState({
  selection,
  ikDragActive = false,
  robotLinks,
  robotJoints,
  rootLinkId,
}: ResolveIkToolSelectionStateOptions): IkToolSelectionState {
  const currentLinkId =
    selection?.type === 'link' && typeof selection.id === 'string' && selection.id.length > 0
      ? selection.id
      : null;

  if (!currentLinkId) {
    return {
      status: 'idle',
      currentLinkId: null,
      selectedLinkId: null,
    };
  }

  const selectedLinkId = resolveSelectedIkDragLinkId({
    selection,
    ikDragActive,
    robotLinks: robotLinks ?? undefined,
    robotJoints: robotJoints ?? undefined,
    rootLinkId: rootLinkId ?? undefined,
  });

  if (selectedLinkId) {
    return {
      status: 'selected',
      currentLinkId,
      selectedLinkId,
    };
  }

  if (!ikDragActive || !robotLinks || !robotJoints || !rootLinkId) {
    return {
      status: 'idle',
      currentLinkId,
      selectedLinkId: null,
    };
  }

  if (currentLinkId === rootLinkId) {
    return {
      status: 'root_not_draggable',
      currentLinkId,
      selectedLinkId: null,
    };
  }

  return {
    status: 'no_variable_chain',
    currentLinkId,
    selectedLinkId: null,
  };
}
