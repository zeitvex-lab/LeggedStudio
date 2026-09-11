import { useState, useRef, useCallback, useEffect } from 'react';
import {
  WORKSPACE_OVERLAY_LEFT_INSET_VAR,
  WORKSPACE_OVERLAY_RIGHT_INSET_VAR,
} from '@/shared/components/3d/scene/viewerOverlaySafeArea';

type PanelType = 'options' | 'joints' | 'measure' | 'paint';
type PanelPosition = { x: number; y: number };

interface DragStart {
  mouseX: number;
  mouseY: number;
  panelX: number;
  panelY: number;
}

interface PositionMap {
  options: PanelPosition | null;
  joints: PanelPosition | null;
  measure: PanelPosition | null;
  paint: PanelPosition | null;
}

const PANEL_EDGE_PADDING = 2;
const MIN_VISIBLE_PANEL_WIDTH = 56;
const MIN_VISIBLE_PANEL_HEADER_HEIGHT = 40;

const readCssPixelValue = (value: string | undefined): number => {
  if (!value) return 0;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
};

const readWorkspaceOverlayInsets = (element: HTMLElement) => {
  const style = window.getComputedStyle(element);
  return {
    left: readCssPixelValue(style.getPropertyValue(WORKSPACE_OVERLAY_LEFT_INSET_VAR)),
    right: readCssPixelValue(style.getPropertyValue(WORKSPACE_OVERLAY_RIGHT_INSET_VAR)),
  };
};

export function usePanelDrag(
  containerRef: React.RefObject<HTMLDivElement | null>,
  optionsPanelRef: React.RefObject<HTMLDivElement | null>,
  jointPanelRef: React.RefObject<HTMLDivElement | null>,
  measurePanelRef: React.RefObject<HTMLDivElement | null>,
  paintPanelRef: React.RefObject<HTMLDivElement | null>
) {
  const [dragging, setDragging] = useState<PanelType | null>(null);
  const dragStartRef = useRef<DragStart | null>(null);
  const activePanelRef = useRef<PanelType | null>(null);
  const liveDragPositionRef = useRef<PanelPosition | null>(null);
  const documentListenersAttachedRef = useRef(false);
  const detachDocumentListenersRef = useRef<() => void>(() => {});
  const bodyUserSelectRef = useRef<string>('');
  const bodyCursorRef = useRef<string>('');
  const positionsRef = useRef<PositionMap>({
    options: null,
    joints: null,
    measure: null,
    paint: null,
  });

  const [optionsPanelPos, setOptionsPanelPos] = useState<PanelPosition | null>(null);
  const [jointPanelPos, setJointPanelPos] = useState<PanelPosition | null>(null);
  const [measurePanelPos, setMeasurePanelPos] = useState<PanelPosition | null>(null);
  const [paintPanelPos, setPaintPanelPos] = useState<PanelPosition | null>(null);

  const getPanelRef = useCallback((panel: PanelType) => {
    if (panel === 'options') return optionsPanelRef;
    if (panel === 'joints') return jointPanelRef;
    if (panel === 'paint') return paintPanelRef;
    return measurePanelRef;
  }, [jointPanelRef, measurePanelRef, optionsPanelRef, paintPanelRef]);

  const getCommittedPosition = useCallback((panel: PanelType) => {
    return positionsRef.current[panel];
  }, []);

  const commitPanelPosition = useCallback((panel: PanelType, position: PanelPosition | null) => {
    positionsRef.current[panel] = position;

    if (panel === 'options') {
      setOptionsPanelPos(position);
      return;
    }

    if (panel === 'joints') {
      setJointPanelPos(position);
      return;
    }

    if (panel === 'paint') {
      setPaintPanelPos(position);
      return;
    }

    setMeasurePanelPos(position);
  }, []);

  const applyPanelPosition = useCallback((panelRef: React.RefObject<HTMLDivElement | null>, position: PanelPosition) => {
    if (!panelRef.current) return;

    panelRef.current.style.left = `${position.x}px`;
    panelRef.current.style.top = `${position.y}px`;
    panelRef.current.style.right = 'auto';
    panelRef.current.style.bottom = 'auto';
    panelRef.current.style.transform = 'none';
  }, []);

  const clampPosition = useCallback((position: PanelPosition, panelRef: React.RefObject<HTMLDivElement | null>) => {
    if (!containerRef.current || !panelRef.current) {
      return position;
    }

    const containerRect = containerRef.current.getBoundingClientRect();
    const panelRect = panelRef.current.getBoundingClientRect();
    const overlayInsets = readWorkspaceOverlayInsets(containerRef.current);
    const minX =
      overlayInsets.left > 0
        ? overlayInsets.left + PANEL_EDGE_PADDING
        : Math.min(PANEL_EDGE_PADDING, MIN_VISIBLE_PANEL_WIDTH - panelRect.width);
    const maxX = Math.max(
      overlayInsets.left + PANEL_EDGE_PADDING,
      containerRect.width - overlayInsets.right - panelRect.width - PANEL_EDGE_PADDING,
    );
    const minY = PANEL_EDGE_PADDING;
    // Ensure title bar stays visible: maxY should keep at least MIN_VISIBLE_PANEL_HEADER_HEIGHT of the panel visible at the bottom
    const maxY = containerRect.height - MIN_VISIBLE_PANEL_HEADER_HEIGHT - PANEL_EDGE_PADDING;

    return {
      x: Math.max(minX, Math.min(position.x, maxX)),
      y: Math.max(minY, Math.min(position.y, maxY)),
    };
  }, [containerRef]);

  // Tighter clamping for container resize — keeps the entire panel visible
  // (drag clamping allows peeking with only MIN_VISIBLE_PANEL_WIDTH visible).
  const clampPositionFullyVisible = useCallback((position: PanelPosition, panelRef: React.RefObject<HTMLDivElement | null>) => {
    if (!containerRef.current || !panelRef.current) {
      return position;
    }

    const containerRect = containerRef.current.getBoundingClientRect();
    const panelRect = panelRef.current.getBoundingClientRect();
    const overlayInsets = readWorkspaceOverlayInsets(containerRef.current);
    const minX = overlayInsets.left + PANEL_EDGE_PADDING;
    const maxX = Math.max(
      minX,
      containerRect.width - overlayInsets.right - panelRect.width - PANEL_EDGE_PADDING,
    );
    const maxY = Math.max(PANEL_EDGE_PADDING, containerRect.height - panelRect.height - PANEL_EDGE_PADDING);

    return {
      x: Math.max(minX, Math.min(position.x, maxX)),
      y: Math.max(PANEL_EDGE_PADDING, Math.min(position.y, maxY)),
    };
  }, [containerRef]);

  const reclampCommittedPositions = useCallback((options?: { requireOverlayInset?: boolean }) => {
    if (activePanelRef.current || !containerRef.current) {
      return;
    }

    if (options?.requireOverlayInset) {
      const overlayInsets = readWorkspaceOverlayInsets(containerRef.current);
      if (overlayInsets.left <= 0 && overlayInsets.right <= 0) {
        return;
      }
    }

    const nextOptions = positionsRef.current.options
      ? clampPositionFullyVisible(positionsRef.current.options, optionsPanelRef)
      : null;
    const nextJoints = positionsRef.current.joints
      ? clampPositionFullyVisible(positionsRef.current.joints, jointPanelRef)
      : null;
    const nextMeasure = positionsRef.current.measure
      ? clampPositionFullyVisible(positionsRef.current.measure, measurePanelRef)
      : null;
    const nextPaint = positionsRef.current.paint
      ? clampPositionFullyVisible(positionsRef.current.paint, paintPanelRef)
      : null;

    if (
      nextOptions &&
      positionsRef.current.options &&
      (nextOptions.x !== positionsRef.current.options.x ||
        nextOptions.y !== positionsRef.current.options.y)
    ) {
      commitPanelPosition('options', nextOptions);
    }
    if (
      nextJoints &&
      positionsRef.current.joints &&
      (nextJoints.x !== positionsRef.current.joints.x ||
        nextJoints.y !== positionsRef.current.joints.y)
    ) {
      commitPanelPosition('joints', nextJoints);
    }
    if (
      nextMeasure &&
      positionsRef.current.measure &&
      (nextMeasure.x !== positionsRef.current.measure.x ||
        nextMeasure.y !== positionsRef.current.measure.y)
    ) {
      commitPanelPosition('measure', nextMeasure);
    }
    if (
      nextPaint &&
      positionsRef.current.paint &&
      (nextPaint.x !== positionsRef.current.paint.x ||
        nextPaint.y !== positionsRef.current.paint.y)
    ) {
      commitPanelPosition('paint', nextPaint);
    }
  }, [
    clampPositionFullyVisible,
    commitPanelPosition,
    containerRef,
    jointPanelRef,
    measurePanelRef,
    optionsPanelRef,
    paintPanelRef,
  ]);

  const updatePositionFromPointer = useCallback((clientX: number, clientY: number) => {
    const activePanel = activePanelRef.current;
    if (!activePanel || !dragStartRef.current) return;

    const panelRef = getPanelRef(activePanel);
    if (!panelRef.current) return;

    const nextPosition = clampPosition({
      x: dragStartRef.current.panelX + (clientX - dragStartRef.current.mouseX),
      y: dragStartRef.current.panelY + (clientY - dragStartRef.current.mouseY),
    }, panelRef);

    liveDragPositionRef.current = nextPosition;
    applyPanelPosition(panelRef, nextPosition);
  }, [applyPanelPosition, clampPosition, getPanelRef]);

  const finalizeDrag = useCallback(() => {
    const activePanel = activePanelRef.current;
    const livePosition = liveDragPositionRef.current;

    if (activePanel && livePosition) {
      commitPanelPosition(activePanel, livePosition);
    }

    document.body.style.userSelect = bodyUserSelectRef.current;
    document.body.style.cursor = bodyCursorRef.current;

    activePanelRef.current = null;
    liveDragPositionRef.current = null;
    dragStartRef.current = null;
    setDragging(null);
    detachDocumentListenersRef.current();
  }, [commitPanelPosition]);

  const handleDocumentMouseMoveRef = useRef<(event: MouseEvent) => void>(() => {});
  const handleDocumentMouseUpRef = useRef<() => void>(() => {});

  handleDocumentMouseMoveRef.current = (event: MouseEvent) => {
    updatePositionFromPointer(event.clientX, event.clientY);
  };
  handleDocumentMouseUpRef.current = () => {
    finalizeDrag();
  };

  const attachDocumentListeners = useCallback(() => {
    if (documentListenersAttachedRef.current) return;

    const handleMouseMove = (event: MouseEvent) => {
      handleDocumentMouseMoveRef.current(event);
    };
    const handleMouseUp = () => {
      handleDocumentMouseUpRef.current();
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    window.addEventListener('blur', handleMouseUp);

    documentListenersAttachedRef.current = true;

    // Reuse the DOM node for detach without rebuilding closures.
    (attachDocumentListeners as typeof attachDocumentListeners & {
      mouseMove?: (event: MouseEvent) => void;
      mouseUp?: () => void;
    }).mouseMove = handleMouseMove;
    (attachDocumentListeners as typeof attachDocumentListeners & {
      mouseMove?: (event: MouseEvent) => void;
      mouseUp?: () => void;
    }).mouseUp = handleMouseUp;
  }, []);

  const detachDocumentListeners = useCallback(() => {
    if (!documentListenersAttachedRef.current) return;

    const mouseMove = (attachDocumentListeners as typeof attachDocumentListeners & {
      mouseMove?: (event: MouseEvent) => void;
    }).mouseMove;
    const mouseUp = (attachDocumentListeners as typeof attachDocumentListeners & {
      mouseUp?: () => void;
    }).mouseUp;

    if (mouseMove) {
      document.removeEventListener('mousemove', mouseMove);
    }
    if (mouseUp) {
      document.removeEventListener('mouseup', mouseUp);
      window.removeEventListener('blur', mouseUp);
    }

    documentListenersAttachedRef.current = false;
  }, [attachDocumentListeners]);

  detachDocumentListenersRef.current = detachDocumentListeners;

  const handleMouseDown = useCallback((panel: PanelType, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const panelRef = getPanelRef(panel);
    if (!panelRef.current || !containerRef.current) return;

    const rect = panelRef.current.getBoundingClientRect();
    const containerRect = containerRef.current.getBoundingClientRect();
    const currentPos = getCommittedPosition(panel);

    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      panelX: currentPos ? currentPos.x : rect.left - containerRect.left,
      panelY: currentPos ? currentPos.y : rect.top - containerRect.top,
    };
    activePanelRef.current = panel;
    liveDragPositionRef.current = currentPos ?? {
      x: rect.left - containerRect.left,
      y: rect.top - containerRect.top,
    };
    bodyUserSelectRef.current = document.body.style.userSelect;
    bodyCursorRef.current = document.body.style.cursor;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
    setDragging(panel);
    attachDocumentListeners();
  }, [attachDocumentListeners, containerRef, getCommittedPosition, getPanelRef]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    updatePositionFromPointer(e.clientX, e.clientY);
  }, [updatePositionFromPointer]);

  const handleMouseUp = useCallback(() => {
    finalizeDrag();
  }, [finalizeDrag]);

  useEffect(() => {
    return () => {
      detachDocumentListeners();
    };
  }, [detachDocumentListeners]);

  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver(() => {
      reclampCommittedPositions();
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [containerRef, reclampCommittedPositions]);

  useEffect(() => {
    reclampCommittedPositions({ requireOverlayInset: true });
  });

  return {
    optionsPanelPos,
    jointPanelPos,
    measurePanelPos,
    paintPanelPos,
    dragging,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
  };
}
