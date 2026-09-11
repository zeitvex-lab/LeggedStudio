import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent, RefObject } from 'react';
import { useUIStore } from '@/store/uiStore';
import { usePointerResize } from '@/shared/hooks/usePointerResize';

const TREE_SIDEBAR_MIN_WIDTH = 220;
const TREE_SIDEBAR_MAX_WIDTH = 520;
const TREE_FILE_BROWSER_MIN_HEIGHT = 40;
const TREE_FILE_BROWSER_MAX_HEIGHT = 1200;
const TREE_JOINT_PANEL_MIN_HEIGHT = 40;
const TREE_JOINT_PANEL_MAX_HEIGHT = 1200;
const TREE_BALANCED_PANEL_FALLBACK_HEIGHT = 240;
// Keep the structure-tree section (its header/tab + a little content) on screen no matter how far
// the file browser / joint panels are dragged or how short the sidebar becomes.
const TREE_STRUCTURE_MIN_HEIGHT = 96;
// Approximate height a collapsed, header-only section occupies. Reserved so a collapsed section's
// toggle stays visible.
const TREE_COLLAPSED_SECTION_HEIGHT = 36;
const TREE_EDITOR_FILE_BROWSER_SECTION_KEY = 'tree_editor_file_browser';
const TREE_EDITOR_STRUCTURE_SECTION_KEY = 'tree_editor_structure';
const TREE_EDITOR_JOINT_SECTION_KEY = 'tree_editor_joint_panel';

function applyTreeSidebarWidth(node: HTMLDivElement | null, width: number) {
  if (!node) {
    return;
  }

  const widthPx = `${Math.round(width)}px`;
  node.style.width = widthPx;
  node.style.minWidth = widthPx;
  node.style.flex = `0 0 ${widthPx}`;
}

interface UseTreeEditorLayoutOptions {
  hasJointPanel?: boolean;
}

interface UseTreeEditorLayoutResult {
  contentRef: RefObject<HTMLDivElement | null>;
  sidebarRef: RefObject<HTMLDivElement | null>;
  width: number;
  fileBrowserHeight: number;
  jointPanelHeight: number;
  isDragging: boolean;
  isFileBrowserOpen: boolean;
  isStructureOpen: boolean;
  setIsFileBrowserOpen: (isOpen: boolean) => void;
  setIsStructureOpen: (isOpen: boolean) => void;
  handleHorizontalResizeStart: (event: ReactMouseEvent) => void;
  handleVerticalResizeStart: (event: ReactMouseEvent) => void;
  handleJointPanelResizeStart: (event: ReactMouseEvent) => void;
}

export function resolveBalancedTreePanelHeight(
  availableHeight: number | null,
  panelCount: number,
): number {
  if (!availableHeight || !Number.isFinite(availableHeight) || availableHeight <= 0) {
    return TREE_BALANCED_PANEL_FALLBACK_HEIGHT;
  }

  const normalizedPanelCount = Math.max(1, Math.floor(panelCount));
  const balancedHeight = Math.floor(availableHeight / normalizedPanelCount);
  return Math.min(
    TREE_FILE_BROWSER_MAX_HEIGHT,
    Math.max(TREE_FILE_BROWSER_MIN_HEIGHT, balancedHeight),
  );
}

export function useTreeEditorLayout({
  hasJointPanel = true,
}: UseTreeEditorLayoutOptions = {}): UseTreeEditorLayoutResult {
  const contentRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState<number | null>(null);
  const width = useUIStore((state) => state.panelLayout.treeSidebarWidth);
  const storedFileBrowserHeight = useUIStore(
    (state) => state.panelLayout.treeFileBrowserHeight,
  );
  const storedJointPanelHeight = useUIStore((state) => state.panelLayout.treeJointPanelHeight);
  const treePanelHeightMode = useUIStore((state) => state.panelLayout.treePanelHeightMode);
  const panelSections = useUIStore((state) => state.panelSections);
  const setPanelLayout = useUIStore((state) => state.setPanelLayout);
  const setPanelSection = useUIStore((state) => state.setPanelSection);
  const isFileBrowserOpen = !(panelSections[TREE_EDITOR_FILE_BROWSER_SECTION_KEY] ?? false);
  const isStructureOpen = !(panelSections[TREE_EDITOR_STRUCTURE_SECTION_KEY] ?? false);
  const isJointPanelCollapsed = panelSections[TREE_EDITOR_JOINT_SECTION_KEY] ?? false;
  const balancedPanelHeight = useMemo(
    () => resolveBalancedTreePanelHeight(contentHeight, hasJointPanel ? 3 : 2),
    [contentHeight, hasJointPanel],
  );
  const usesBalancedPanelHeights = treePanelHeightMode === 'balanced';
  const rawFileBrowserHeight = usesBalancedPanelHeights
    ? balancedPanelHeight
    : storedFileBrowserHeight;
  const rawJointPanelHeight = usesBalancedPanelHeights
    ? balancedPanelHeight
    : storedJointPanelHeight;

  // The file browser and joint panels are fixed-height (shrink-0) while the structure tree absorbs
  // the remaining space. Without bounding the fixed panels against the available content height,
  // dragging them long enough pushes the structure-tree section — and its header/tab — off screen.
  // Bound each panel so the structure section always keeps at least `structureReserve` px.
  const hasMeasuredContentHeight =
    typeof contentHeight === 'number' && Number.isFinite(contentHeight) && contentHeight > 0;
  const structureReserve = isStructureOpen
    ? TREE_STRUCTURE_MIN_HEIGHT
    : TREE_COLLAPSED_SECTION_HEIGHT;
  const jointContribution = !hasJointPanel
    ? 0
    : isJointPanelCollapsed
      ? TREE_COLLAPSED_SECTION_HEIGHT
      : rawJointPanelHeight;

  const fileBrowserMax = hasMeasuredContentHeight
    ? Math.max(
        TREE_FILE_BROWSER_MIN_HEIGHT,
        Math.min(
          TREE_FILE_BROWSER_MAX_HEIGHT,
          (contentHeight as number) - structureReserve - jointContribution,
        ),
      )
    : TREE_FILE_BROWSER_MAX_HEIGHT;
  const fileBrowserHeight = Math.min(rawFileBrowserHeight, fileBrowserMax);

  // Joints sit below the file browser, so bound them against the file browser's clamped height too.
  const fileBrowserContribution = isFileBrowserOpen
    ? fileBrowserHeight
    : TREE_COLLAPSED_SECTION_HEIGHT;
  const jointPanelMax = hasMeasuredContentHeight
    ? Math.max(
        TREE_JOINT_PANEL_MIN_HEIGHT,
        Math.min(
          TREE_JOINT_PANEL_MAX_HEIGHT,
          (contentHeight as number) - structureReserve - fileBrowserContribution,
        ),
      )
    : TREE_JOINT_PANEL_MAX_HEIGHT;
  const jointPanelHeight = Math.min(rawJointPanelHeight, jointPanelMax);

  const updateContentHeight = useCallback((height: number) => {
    if (!Number.isFinite(height) || height <= 0) {
      return;
    }

    setContentHeight((previousHeight) =>
      previousHeight === Math.round(height) ? previousHeight : Math.round(height),
    );
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    const node = contentRef.current;
    if (!node) {
      return undefined;
    }

    const measure = () => {
      const rectHeight = node.getBoundingClientRect().height;
      updateContentHeight(rectHeight || node.clientHeight);
    };

    const frameId =
      typeof window.requestAnimationFrame === 'function'
        ? window.requestAnimationFrame(measure)
        : null;

    const ResizeObserverConstructor =
      typeof ResizeObserver === 'undefined' ? null : ResizeObserver;

    if (ResizeObserverConstructor) {
      const observer = new ResizeObserverConstructor((entries) => {
        const nextHeight = entries[0]?.contentRect?.height;
        updateContentHeight(nextHeight ?? node.clientHeight);
      });
      observer.observe(node);

      return () => {
        if (frameId !== null && typeof window.cancelAnimationFrame === 'function') {
          window.cancelAnimationFrame(frameId);
        }
        observer.disconnect();
      };
    }

    window.addEventListener('resize', measure);

    return () => {
      if (frameId !== null && typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(frameId);
      }
      window.removeEventListener('resize', measure);
    };
  }, [updateContentHeight]);

  const setIsFileBrowserOpen = useCallback(
    (isOpen: boolean) => {
      setPanelSection(TREE_EDITOR_FILE_BROWSER_SECTION_KEY, !isOpen);
    },
    [setPanelSection],
  );

  const setIsStructureOpen = useCallback(
    (isOpen: boolean) => {
      setPanelSection(TREE_EDITOR_STRUCTURE_SECTION_KEY, !isOpen);
    },
    [setPanelSection],
  );

  const horizontalResize = usePointerResize({
    axis: 'x',
    cursor: 'col-resize',
    min: TREE_SIDEBAR_MIN_WIDTH,
    max: TREE_SIDEBAR_MAX_WIDTH,
    value: width,
    onChange: (nextWidth) => applyTreeSidebarWidth(sidebarRef.current, nextWidth),
    onCommit: (nextWidth) => setPanelLayout('treeSidebarWidth', nextWidth),
  });

  const verticalResize = usePointerResize({
    axis: 'y',
    cursor: 'row-resize',
    min: TREE_FILE_BROWSER_MIN_HEIGHT,
    max: fileBrowserMax,
    value: fileBrowserHeight,
    onChange: (nextHeight) => setPanelLayout('treeFileBrowserHeight', nextHeight),
  });

  const jointPanelResize = usePointerResize({
    axis: 'y',
    cursor: 'row-resize',
    min: TREE_JOINT_PANEL_MIN_HEIGHT,
    max: jointPanelMax,
    value: jointPanelHeight,
    onChange: (nextHeight) => setPanelLayout('treeJointPanelHeight', nextHeight),
  });

  const activateCustomTreePanelHeights = useCallback(() => {
    if (treePanelHeightMode === 'custom') {
      return;
    }

    setPanelLayout('treeFileBrowserHeight', fileBrowserHeight);
    setPanelLayout('treeJointPanelHeight', jointPanelHeight);
    setPanelLayout('treePanelHeightMode', 'custom');
  }, [fileBrowserHeight, jointPanelHeight, setPanelLayout, treePanelHeightMode]);

  const handleVerticalResizeStart = useCallback(
    (event: ReactMouseEvent) => {
      activateCustomTreePanelHeights();
      verticalResize.handleResizeStart(event);
    },
    [activateCustomTreePanelHeights, verticalResize.handleResizeStart],
  );

  const handleJointPanelResizeStart = useCallback(
    (event: ReactMouseEvent) => {
      activateCustomTreePanelHeights();
      jointPanelResize.handleResizeStart(event);
    },
    [activateCustomTreePanelHeights, jointPanelResize.handleResizeStart],
  );

  return {
    contentRef,
    sidebarRef,
    width,
    fileBrowserHeight,
    jointPanelHeight,
    isDragging:
      horizontalResize.isDragging || verticalResize.isDragging || jointPanelResize.isDragging,
    isFileBrowserOpen,
    isStructureOpen,
    setIsFileBrowserOpen,
    setIsStructureOpen,
    handleHorizontalResizeStart: horizontalResize.handleResizeStart,
    handleVerticalResizeStart,
    handleJointPanelResizeStart,
  };
}
