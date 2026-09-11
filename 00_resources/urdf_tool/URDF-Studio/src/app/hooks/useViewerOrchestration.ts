import { useCallback, useEffect, useRef, type RefObject } from 'react';

import { useSelectionStore, useUIStore } from '@/store';
import {
  areEntityRefsEqual,
  type AssemblyState,
  type DetailLinkTab,
  type EntityRef,
  type WorkspaceSelection,
} from '@/types';

type LinkEntityRef = Extract<EntityRef, { type: 'link' }>;

function resolveDetailLinkTab(subType: 'visual' | 'collision'): DetailLinkTab {
  return subType;
}

interface UseViewerOrchestrationOptions {
  workspace: AssemblyState;
  setSelection: (selection: WorkspaceSelection) => void;
  pulseSelection: (selection: WorkspaceSelection, durationMs?: number) => void;
  setHoveredSelection: (selection: WorkspaceSelection) => void;
  focusOn: (ref: EntityRef) => void;
  transformPendingRef: RefObject<boolean>;
}

/** Resolve attention by exact component ownership and source-local IDs. */
export function resolveParentJointAttentionSelection(
  workspace: AssemblyState,
  linkRef: LinkEntityRef,
): WorkspaceSelection {
  const component = workspace.components[linkRef.componentId];
  if (!component?.robot.links[linkRef.entityId]) {
    return null;
  }
  const parentJoint = Object.values(component.robot.joints).find(
    (joint) => joint.childLinkId === linkRef.entityId,
  );
  return parentJoint
    ? {
        entity: {
          type: 'joint',
          componentId: linkRef.componentId,
          entityId: parentJoint.id,
        },
      }
    : null;
}

export function useViewerOrchestration({
  workspace,
  setSelection,
  pulseSelection,
  setHoveredSelection,
  focusOn,
  transformPendingRef,
}: UseViewerOrchestrationOptions) {
  const isInteractionAllowed = useCallback(
    (selection: WorkspaceSelection) =>
      useSelectionStore.getState().isInteractionAllowed(selection),
    [],
  );

  const ensureCollisionVisible = useCallback(() => {
    const uiState = useUIStore.getState();
    if (!uiState.viewOptions.showCollision) {
      uiState.setViewOption('showCollision', true);
    }
  }, []);

  const applyHelperSelectionUiState = useCallback(
    (helperKind: NonNullable<WorkspaceSelection>['helperKind']) => {
      if (!helperKind) return;
      const uiState = useUIStore.getState();
      if (helperKind === 'center-of-mass' || helperKind === 'inertia') {
        if (uiState.detailLinkTab !== 'physics') uiState.setDetailLinkTab('physics');
        uiState.setPanelSection('property_editor_link_inertial', false);
      } else if (helperKind === 'origin-axes') {
        if (uiState.detailLinkTab !== 'visual') uiState.setDetailLinkTab('visual');
        uiState.setPanelSection('property_editor_link_frame', false);
      } else if (helperKind === 'joint-axis') {
        uiState.setPanelSection('kinematics', false);
      }
    },
    [],
  );

  const preserveCollisionObjectIndex = useCallback(
    (selection: WorkspaceSelection): WorkspaceSelection => {
      if (
        !selection
        || selection.entity.type !== 'link'
        || selection.subType !== 'collision'
        || selection.objectIndex !== undefined
      ) {
        return selection;
      }
      const current = useSelectionStore.getState().selection;
      return current
        && current.entity.type === 'link'
        && areEntityRefsEqual(current.entity, selection.entity)
        && current.subType === 'collision'
        && current.objectIndex !== undefined
        ? { ...selection, objectIndex: current.objectIndex }
        : selection;
    },
    [],
  );

  const preserveHoveredHighlightObject = useCallback(
    (selection: WorkspaceSelection): WorkspaceSelection => {
      if (!selection || selection.entity.type !== 'link' || !selection.subType) {
        return selection;
      }
      const hovered = useSelectionStore.getState().hoveredSelection;
      return hovered
        && hovered.entity.type === 'link'
        && areEntityRefsEqual(hovered.entity, selection.entity)
        && hovered.subType === selection.subType
        && hovered.objectIndex === selection.objectIndex
        && hovered.highlightObjectId !== undefined
        ? { ...selection, highlightObjectId: hovered.highlightObjectId }
        : selection;
    },
    [],
  );

  const revealSelection = useCallback(
    (selection: WorkspaceSelection, suppressAutoReveal = false) => {
      if (!selection || selection.entity.type !== 'link' || !selection.subType) return;
      if (selection.subType === 'collision' && !suppressAutoReveal) {
        ensureCollisionVisible();
      }
      const uiState = useUIStore.getState();
      const nextTab = resolveDetailLinkTab(selection.subType);
      if (uiState.detailLinkTab !== nextTab) uiState.setDetailLinkTab(nextTab);
    },
    [ensureCollisionVisible],
  );

  const resolveAttentionSelection = useCallback(
    (selection: WorkspaceSelection): WorkspaceSelection => {
      if (
        !selection
        || selection.entity.type !== 'link'
        || selection.helperKind
      ) {
        return selection;
      }
      return resolveParentJointAttentionSelection(workspace, selection.entity) ?? selection;
    },
    [workspace],
  );

  const handleSelect = useCallback(
    (selection: WorkspaceSelection) => {
      if (transformPendingRef.current) return;
      const next = preserveCollisionObjectIndex(selection);
      if (!isInteractionAllowed(next)) return;
      revealSelection(next);
      setSelection(next);
    },
    [
      isInteractionAllowed,
      preserveCollisionObjectIndex,
      revealSelection,
      setSelection,
      transformPendingRef,
    ],
  );

  const handleSelectGeometry = useCallback(
    (
      ref: LinkEntityRef,
      subType: 'visual' | 'collision',
      objectIndex = 0,
      suppressPulse = false,
      suppressAutoReveal = false,
    ) => {
      if (transformPendingRef.current) return;
      const next: WorkspaceSelection = { entity: ref, subType, objectIndex };
      if (!isInteractionAllowed(next)) return;
      revealSelection(next, suppressAutoReveal);
      setSelection(next);
      if (!suppressPulse) pulseSelection(next);
    },
    [isInteractionAllowed, pulseSelection, revealSelection, setSelection, transformPendingRef],
  );

  const handleViewerSelect = useCallback(
    (selection: WorkspaceSelection) => {
      if (transformPendingRef.current) return;
      if (!selection) {
        setSelection(null);
        setHoveredSelection(null);
        pulseSelection(null);
        return;
      }
      const next = preserveCollisionObjectIndex(
        preserveHoveredHighlightObject(selection),
      );
      if (!next) return;
      if (!isInteractionAllowed(next)) return;
      revealSelection(next);
      setSelection(next);
      if (next.helperKind) {
        setHoveredSelection(null);
        applyHelperSelectionUiState(next.helperKind);
      }
      pulseSelection(resolveAttentionSelection(next));
    },
    [
      applyHelperSelectionUiState,
      isInteractionAllowed,
      preserveCollisionObjectIndex,
      preserveHoveredHighlightObject,
      pulseSelection,
      resolveAttentionSelection,
      revealSelection,
      setHoveredSelection,
      setSelection,
      transformPendingRef,
    ],
  );

  const handleTransformPendingChange = useCallback(
    (pending: boolean) => {
      transformPendingRef.current = pending;
    },
    [transformPendingRef],
  );

  const lastHoverDispatchTimeRef = useRef(0);
  const pendingHoverRef = useRef<WorkspaceSelection>(null);
  const hasPendingHoverRef = useRef(false);
  const hoverRafRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (hoverRafRef.current !== null && typeof window !== 'undefined') {
      window.cancelAnimationFrame(hoverRafRef.current);
    }
    hoverRafRef.current = null;
    hasPendingHoverRef.current = false;
  }, []);

  const dispatchHoverNow = useCallback(
    (selection: WorkspaceSelection) => {
      const selected = useSelectionStore.getState().selection;
      const hovered = useSelectionStore.getState().hoveredSelection;
      if (
        selection
        && selected
        && hovered
        && selection.entity.type === 'link'
        && selected.entity.type === 'link'
        && areEntityRefsEqual(selection.entity, selected.entity)
        && areEntityRefsEqual(hovered.entity, selected.entity)
      ) {
        return;
      }
      if (!isInteractionAllowed(selection)) {
        setHoveredSelection(null);
        return;
      }
      setHoveredSelection(selection);
    },
    [isInteractionAllowed, setHoveredSelection],
  );

  const handleHover = useCallback(
    (selection: WorkspaceSelection) => {
      if (typeof window === 'undefined') {
        dispatchHoverNow(selection);
        return;
      }
      const now = performance.now();
      if (hoverRafRef.current === null && now - lastHoverDispatchTimeRef.current >= 16) {
        lastHoverDispatchTimeRef.current = now;
        dispatchHoverNow(selection);
        return;
      }
      pendingHoverRef.current = selection;
      hasPendingHoverRef.current = true;
      if (hoverRafRef.current !== null) return;
      hoverRafRef.current = window.requestAnimationFrame(() => {
        hoverRafRef.current = null;
        if (!hasPendingHoverRef.current) return;
        hasPendingHoverRef.current = false;
        lastHoverDispatchTimeRef.current = performance.now();
        dispatchHoverNow(pendingHoverRef.current);
      });
    },
    [dispatchHoverNow],
  );

  const handleFocus = useCallback((ref: EntityRef) => focusOn(ref), [focusOn]);

  return {
    handleSelect,
    handleSelectGeometry,
    handleViewerSelect,
    handleTransformPendingChange,
    handleHover,
    handleFocus,
  };
}
