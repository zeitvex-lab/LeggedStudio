import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';

interface UseTreeEditorLayoutOptions {
  collapsed?: boolean;
}

export function useTreeEditorLayout({ collapsed }: UseTreeEditorLayoutOptions) {
  const [width, setWidth] = useState(288);
  const [isDragging, setIsDragging] = useState(false);
  const isResizing = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const [fileBrowserHeight, setFileBrowserHeight] = useState(250);
  const [isFileBrowserOpen, setIsFileBrowserOpen] = useState(true);
  const [isStructureOpen, setIsStructureOpen] = useState(true);
  const isVerticalResizing = useRef(false);
  const startY = useRef(0);
  const startHeight = useRef(0);
  const bodyCursorRef = useRef('');
  const bodyUserSelectRef = useRef('');

  const captureBodyInteractionStyles = useCallback(() => {
    bodyCursorRef.current = document.body.style.cursor;
    bodyUserSelectRef.current = document.body.style.userSelect;
  }, []);

  const restoreBodyInteractionStyles = useCallback(() => {
    document.body.style.cursor = bodyCursorRef.current;
    document.body.style.userSelect = bodyUserSelectRef.current;
  }, []);

  const handleMouseDown = useCallback((event: ReactMouseEvent) => {
    isResizing.current = true;
    setIsDragging(true);
    startX.current = event.clientX;
    startWidth.current = width;
    captureBodyInteractionStyles();
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [captureBodyInteractionStyles, width]);

  const handleVerticalMouseDown = useCallback((event: ReactMouseEvent) => {
    event.stopPropagation();
    isVerticalResizing.current = true;
    setIsDragging(true);
    startY.current = event.clientY;
    startHeight.current = fileBrowserHeight;
    captureBodyInteractionStyles();
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, [captureBodyInteractionStyles, fileBrowserHeight]);

  const handleMouseMove = useCallback((event: MouseEvent) => {
    if (isResizing.current) {
      const delta = event.clientX - startX.current;
      const nextWidth = Math.max(200, Math.min(600, startWidth.current + delta));
      setWidth(nextWidth);
    }

    if (isVerticalResizing.current) {
      const delta = event.clientY - startY.current;
      const nextHeight = Math.max(100, Math.min(600, startHeight.current + delta));
      setFileBrowserHeight(nextHeight);
    }
  }, []);

  const handleMouseUp = useCallback(() => {
    const wasResizing = isResizing.current || isVerticalResizing.current;

    isResizing.current = false;
    isVerticalResizing.current = false;
    setIsDragging(false);

    if (wasResizing) {
      restoreBodyInteractionStyles();
    }
  }, [restoreBodyInteractionStyles]);

  useEffect(() => {
    if (!isDragging) {
      return undefined;
    }

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    window.addEventListener('blur', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      window.removeEventListener('blur', handleMouseUp);
      restoreBodyInteractionStyles();
    };
  }, [handleMouseMove, handleMouseUp, isDragging, restoreBodyInteractionStyles]);

  const actualWidth = collapsed ? 0 : width;
  const shouldFileBrowserFillSpace = isFileBrowserOpen && !isStructureOpen;

  return {
    actualWidth,
    fileBrowserHeight,
    handleMouseDown,
    handleVerticalMouseDown,
    isDragging,
    isFileBrowserOpen,
    isStructureOpen,
    setIsFileBrowserOpen,
    setIsStructureOpen,
    shouldFileBrowserFillSpace,
  };
}
