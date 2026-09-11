import React, { useCallback, useEffect, useRef } from 'react';

const DEFAULT_REPEAT_DELAY_MS = 350;
const DEFAULT_REPEAT_INTERVAL_MS = 70;

interface PressAndHoldRepeatOptions {
  repeatDelayMs?: number;
  repeatIntervalMs?: number;
}

export function usePressAndHoldRepeat<TAction>(
  onRepeat: (action: TAction) => void,
  {
    repeatDelayMs = DEFAULT_REPEAT_DELAY_MS,
    repeatIntervalMs = DEFAULT_REPEAT_INTERVAL_MS,
  }: PressAndHoldRepeatOptions = {},
) {
  const timeoutRef = useRef<number | null>(null);
  const intervalRef = useRef<number | null>(null);
  const suppressClickRef = useRef(false);
  const onRepeatRef = useRef(onRepeat);

  useEffect(() => {
    onRepeatRef.current = onRepeat;
  }, [onRepeat]);

  const clearTimers = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const invokeRepeat = useCallback((action: TAction) => {
    onRepeatRef.current(action);
  }, []);

  const startPressAndHold = useCallback(
    (action: TAction) => {
      clearTimers();
      suppressClickRef.current = true;
      invokeRepeat(action);
      timeoutRef.current = window.setTimeout(() => {
        intervalRef.current = window.setInterval(() => {
          invokeRepeat(action);
        }, repeatIntervalMs);
      }, repeatDelayMs);
    },
    [clearTimers, invokeRepeat, repeatDelayMs, repeatIntervalMs],
  );

  const stopPressAndHold = useCallback(() => {
    clearTimers();
  }, [clearTimers]);

  const repeatButtonProps = useCallback(
    (action: TAction, label: string): React.ButtonHTMLAttributes<HTMLButtonElement> => ({
      type: 'button',
      'aria-label': label,
      onPointerDown: (event) => {
        event.preventDefault();
        event.currentTarget.setPointerCapture?.(event.pointerId);
        startPressAndHold(action);
      },
      onPointerUp: (event) => {
        if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
          event.currentTarget.releasePointerCapture?.(event.pointerId);
        }
        stopPressAndHold();
      },
      onPointerCancel: () => {
        stopPressAndHold();
        suppressClickRef.current = false;
      },
      onLostPointerCapture: () => {
        stopPressAndHold();
      },
      onClick: (event) => {
        if (suppressClickRef.current) {
          suppressClickRef.current = false;
          event.preventDefault();
          return;
        }
        invokeRepeat(action);
      },
    }),
    [invokeRepeat, startPressAndHold, stopPressAndHold],
  );

  return {
    repeatButtonProps,
    startPressAndHold,
    stopPressAndHold,
  };
}
