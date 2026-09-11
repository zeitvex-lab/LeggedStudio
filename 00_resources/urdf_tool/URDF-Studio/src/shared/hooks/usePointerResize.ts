import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import {
  dispatchPointerResizeEvent,
  POINTER_RESIZE_END_EVENT,
  POINTER_RESIZE_START_EVENT,
} from './pointerResizeEvents';

interface UsePointerResizeOptions {
  axis: 'x' | 'y';
  cursor: 'col-resize' | 'row-resize';
  direction?: 1 | -1;
  max: number;
  min: number;
  onChange: (nextValue: number) => void;
  onCommit?: (nextValue: number) => void;
  value: number;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function usePointerResize({
  axis,
  cursor,
  direction = 1,
  max,
  min,
  onChange,
  onCommit,
  value,
}: UsePointerResizeOptions) {
  const [isDragging, setIsDragging] = useState(false);
  const isResizingRef = useRef(false);
  const lastValueRef = useRef(value);
  const startPointerRef = useRef(0);
  const startValueRef = useRef(value);
  const bodyCursorRef = useRef('');
  const bodyUserSelectRef = useRef('');

  // Use refs for callbacks to avoid re-registering event listeners on every render
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onCommitRef = useRef(onCommit);
  onCommitRef.current = onCommit;
  const axisRef = useRef(axis);
  axisRef.current = axis;
  const directionRef = useRef(direction);
  directionRef.current = direction;
  const minRef = useRef(min);
  minRef.current = min;
  const maxRef = useRef(max);
  maxRef.current = max;

  const captureBodyInteractionStyles = useCallback(() => {
    bodyCursorRef.current = document.body.style.cursor;
    bodyUserSelectRef.current = document.body.style.userSelect;
  }, []);

  const restoreBodyInteractionStyles = useCallback(() => {
    document.body.style.cursor = bodyCursorRef.current;
    document.body.style.userSelect = bodyUserSelectRef.current;
  }, []);

  const handleResizeStart = useCallback((event: ReactMouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    isResizingRef.current = true;
    setIsDragging(true);
    startPointerRef.current = axisRef.current === 'x' ? event.clientX : event.clientY;
    startValueRef.current = value;
    lastValueRef.current = value;
    captureBodyInteractionStyles();
    document.body.style.cursor = cursor;
    document.body.style.userSelect = 'none';
    dispatchPointerResizeEvent(POINTER_RESIZE_START_EVENT);
  }, [captureBodyInteractionStyles, cursor, value]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isResizingRef.current) {
        return;
      }

      const currentPointer = axisRef.current === 'x' ? event.clientX : event.clientY;
      const delta = (currentPointer - startPointerRef.current) * directionRef.current;
      const nextValue = clamp(startValueRef.current + delta, minRef.current, maxRef.current);
      if (nextValue === lastValueRef.current) {
        return;
      }

      lastValueRef.current = nextValue;
      onChangeRef.current(nextValue);
    };

    const handleMouseUp = () => {
      if (!isResizingRef.current) {
        return;
      }

      isResizingRef.current = false;
      onCommitRef.current?.(lastValueRef.current);
      setIsDragging(false);
      restoreBodyInteractionStyles();
      dispatchPointerResizeEvent(POINTER_RESIZE_END_EVENT);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    window.addEventListener('blur', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      window.removeEventListener('blur', handleMouseUp);
      const wasResizing = isResizingRef.current;
      isResizingRef.current = false;
      restoreBodyInteractionStyles();
      if (wasResizing) {
        dispatchPointerResizeEvent(POINTER_RESIZE_END_EVENT);
      }
    };
  }, [restoreBodyInteractionStyles]);

  return {
    handleResizeStart,
    isDragging,
  };
}
