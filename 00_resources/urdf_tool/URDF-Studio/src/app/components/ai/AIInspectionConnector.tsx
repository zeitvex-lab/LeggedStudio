import { useCallback, useMemo, useRef } from 'react';
import { useShallow } from 'zustand/react/shallow';

import {
  AIInspectionModal,
  resolveAIWorkspaceRobotTarget,
} from '@/features/ai-assistant';
import type {
  AIConversationFocusedIssue,
  AIConversationSelection,
} from '@/features/ai-assistant';
import { useSelectionStore } from '@/store/selectionStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { InspectionReport, InteractionSelection, RobotState } from '@/types';
import type { Language } from '@/shared/i18n';

interface AIInspectionConnectorProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Language;
  onOpenConversationWithReport: (
    report: InspectionReport,
    robotSnapshot: RobotState,
    options?: {
      selectedEntity?: AIConversationSelection | null;
      focusedIssue?: AIConversationFocusedIssue | null;
    },
  ) => void;
}

const EMPTY_AI_SNAPSHOT_SELECTION: InteractionSelection = { type: null, id: null };

export function AIInspectionConnector({
  isOpen,
  onClose,
  lang,
  onOpenConversationWithReport,
}: AIInspectionConnectorProps) {
  const workspace = useWorkspaceStore((state) => state.workspace);
  const { selection, setSelection, focusOn, pulseSelection } = useSelectionStore(
    useShallow((state) => ({
      selection: state.selection,
      setSelection: state.setSelection,
      focusOn: state.focusOn,
      pulseSelection: state.pulseSelection,
    })),
  );
  const liveTarget = useMemo(
    () => resolveAIWorkspaceRobotTarget(workspace, selection),
    [selection, workspace],
  );
  const sessionScopeRef = useRef({
    componentId: liveTarget.componentId,
  });
  const wasOpenRef = useRef(false);
  if (!isOpen || !wasOpenRef.current) {
    sessionScopeRef.current = {
      componentId: liveTarget.componentId,
    };
  }
  wasOpenRef.current = isOpen;
  const sessionScope = sessionScopeRef.current;
  const inspectionTarget = useMemo(
    () => resolveAIWorkspaceRobotTarget(
      workspace,
      sessionScope.componentId
        ? { entity: { type: 'component', componentId: sessionScope.componentId } }
        : { entity: { type: 'assembly' } },
    ),
    [sessionScope.componentId, workspace],
  );
  const robot = useMemo<RobotState>(
    () => ({
      ...structuredClone(inspectionTarget.robotData),
      selection: EMPTY_AI_SNAPSHOT_SELECTION,
    }),
    [inspectionTarget.robotData],
  );

  const handleSelectItem = useCallback(
    (type: 'link' | 'joint', snapshotEntityId: string) => {
      const ref = inspectionTarget.resolveSnapshotEntityRef(type, snapshotEntityId);
      if (!ref) {
        return;
      }

      const nextSelection = { entity: ref } as const;
      setSelection(nextSelection);
      pulseSelection(nextSelection);
      focusOn(ref);
    },
    [focusOn, inspectionTarget, pulseSelection, setSelection],
  );

  const handleOpenConversationWithReport = useCallback(
    (
      report: InspectionReport,
      robotSnapshot: RobotState,
      options?: {
        selectedEntity?: { type: 'link' | 'joint'; id: string } | null;
        focusedIssue?: AIConversationFocusedIssue | null;
      },
    ) => {
      const snapshotSelection = options?.selectedEntity;
      const ref = snapshotSelection
        ? inspectionTarget.resolveSnapshotEntityRef(
            snapshotSelection.type,
            snapshotSelection.id,
          )
        : null;

      onOpenConversationWithReport(report, robotSnapshot, {
        focusedIssue: options?.focusedIssue ?? null,
        selectedEntity: ref && snapshotSelection
          ? { ...ref, snapshotEntityId: snapshotSelection.id }
          : null,
      });
    },
    [inspectionTarget, onOpenConversationWithReport],
  );

  return (
    <AIInspectionModal
      isOpen={isOpen}
      onClose={onClose}
      robot={robot}
      lang={lang}
      onSelectItem={handleSelectItem}
      onOpenConversationWithReport={handleOpenConversationWithReport}
    />
  );
}
