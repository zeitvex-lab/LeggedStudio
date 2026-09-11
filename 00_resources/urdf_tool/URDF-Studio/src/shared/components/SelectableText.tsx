import React, { useCallback, useEffect, useRef, useState } from 'react';

export interface SelectableTextProps {
  children: React.ReactNode;
  className?: string;
  longPressMs?: number;
}

export const SelectableText: React.FC<SelectableTextProps> = ({
  children,
  className = '',
  longPressMs = 400,
}) => {
  const [isLongPressing, setIsLongPressing] = useState(false);
  const pressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const elementRef = useRef<HTMLSpanElement>(null);

  const startLongPress = useCallback((event: MouseEvent) => {
    event.preventDefault();

    pressTimerRef.current = setTimeout(() => {
      setIsLongPressing(true);
      if (elementRef.current) {
        elementRef.current.style.userSelect = 'text';
        elementRef.current.style.webkitUserSelect = 'text';
      }
    }, longPressMs);
  }, [longPressMs]);

  const handleMouseUp = useCallback(() => {
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }

    if (!isLongPressing && elementRef.current) {
      elementRef.current.style.userSelect = 'none';
      elementRef.current.style.webkitUserSelect = 'none';
    }

    setIsLongPressing(false);
  }, [isLongPressing]);

  const handleMouseLeave = useCallback(() => {
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }

    setIsLongPressing(false);

    if (elementRef.current) {
      elementRef.current.style.userSelect = 'none';
      elementRef.current.style.webkitUserSelect = 'none';
    }
  }, []);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) {
      return undefined;
    }

    element.addEventListener('mousedown', startLongPress);
    element.addEventListener('mouseup', handleMouseUp);
    element.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      element.removeEventListener('mousedown', startLongPress);
      element.removeEventListener('mouseup', handleMouseUp);
      element.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [handleMouseLeave, handleMouseUp, startLongPress]);

  useEffect(() => {
    return () => {
      if (pressTimerRef.current) {
        clearTimeout(pressTimerRef.current);
      }
    };
  }, []);

  return (
    <span
      ref={elementRef}
      className={className}
      style={{ userSelect: 'none', WebkitUserSelect: 'none' }}
    >
      {children}
    </span>
  );
};
