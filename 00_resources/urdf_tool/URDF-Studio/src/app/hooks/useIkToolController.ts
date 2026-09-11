import { useCallback, useMemo } from 'react';
import { resolveDirectManipulableLinkIkJointIds } from '@/core/robot';
import { resolveIkToolSelectionState } from '../utils/ikToolSelectionState';
import type { RobotData, WorkspaceSelection } from '@/types';

export interface IkToolLinkOption {
  value: string;
  label: string;
}

interface UseIkToolControllerParams {
  ikDragActive: boolean;
  componentId: string;
  robot: RobotData;
  selection: WorkspaceSelection;
  setSelection: (selection: WorkspaceSelection) => void;
}

interface ResolveIkToolLinkOptionsParams {
  robotLinks?: RobotData['links'] | null;
  robotJoints?: RobotData['joints'] | null;
  rootLinkId?: string | null;
}

function resolveLinkOptionLabel(linkId: string, linkName: string | undefined): string {
  if (!linkName || linkName === linkId) {
    return linkId;
  }

  return `${linkName} (${linkId})`;
}

export function resolveIkToolLinkOptions({
  robotLinks,
  robotJoints,
  rootLinkId,
}: ResolveIkToolLinkOptionsParams): IkToolLinkOption[] {
  if (!robotLinks || !robotJoints || !rootLinkId) {
    return [];
  }

  return Object.entries(robotLinks)
    .filter(([linkId]) => linkId !== rootLinkId)
    .filter(([linkId]) => {
      const jointIds = resolveDirectManipulableLinkIkJointIds(
        {
          links: robotLinks,
          joints: robotJoints,
          rootLinkId,
        },
        linkId,
      );

      return Boolean(jointIds?.length);
    })
    .map(([linkId, link]) => ({
      value: linkId,
      label: resolveLinkOptionLabel(linkId, link?.name),
    }))
    .sort((left, right) =>
      left.label.localeCompare(right.label, undefined, {
        numeric: true,
        sensitivity: 'base',
      }),
    );
}

export function useIkToolController({
  ikDragActive,
  componentId,
  robot,
  selection,
  setSelection,
}: UseIkToolControllerParams) {
  const localSelection = useMemo(() => {
    const ref = selection?.entity;
    if (!ref || !('componentId' in ref) || ref.componentId !== componentId) {
      return { type: null, id: null } as const;
    }
    if (ref.type !== 'link' && ref.type !== 'joint' && ref.type !== 'tendon') {
      return { type: null, id: null } as const;
    }
    return {
      type: ref.type,
      id: ref.entityId,
      subType: selection.subType,
      helperKind: selection.helperKind,
    };
  }, [componentId, selection]);
  const ikToolSelectionState = useMemo(
    () =>
      resolveIkToolSelectionState({
        selection: localSelection,
        ikDragActive,
        robotLinks: robot.links,
        robotJoints: robot.joints,
        rootLinkId: robot.rootLinkId,
      }),
    [ikDragActive, localSelection, robot],
  );
  const ikLinkOptions = useMemo(
    () =>
      resolveIkToolLinkOptions({
        robotLinks: robot.links,
        robotJoints: robot.joints,
        rootLinkId: robot.rootLinkId,
      }),
    [robot],
  );
  const selectableIkLinkIds = useMemo(
    () => new Set(ikLinkOptions.map((option) => option.value)),
    [ikLinkOptions],
  );
  const selectedIkLinkId = ikToolSelectionState.selectedLinkId;
  const selectedIkLinkLabel = useMemo(() => {
    if (!selectedIkLinkId) {
      return null;
    }

    return (
      robot.links[selectedIkLinkId]?.name ??
      selectedIkLinkId
    );
  }, [robot.links, selectedIkLinkId]);
  const currentIkLinkLabel = useMemo(() => {
    if (!ikToolSelectionState.currentLinkId) {
      return null;
    }

    return (
      robot.links[ikToolSelectionState.currentLinkId]?.name ??
      ikToolSelectionState.currentLinkId
    );
  }, [ikToolSelectionState.currentLinkId, robot.links]);
  const selectIkLink = useCallback(
    (linkId: string) => {
      if (!selectableIkLinkIds.has(linkId)) {
        return;
      }

      setSelection({
        entity: { type: 'link', componentId, entityId: linkId },
        helperKind: 'ik-handle',
      });
    },
    [componentId, selectableIkLinkIds, setSelection],
  );

  return {
    ikToolSelectionState,
    ikLinkOptions,
    selectedIkLinkId,
    selectedIkLinkLabel,
    currentIkLinkLabel,
    selectIkLink,
  };
}
