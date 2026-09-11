import type { MutableValueRef } from './usdHoverPointerState';

export interface ResolveUsdHoverCameraMotionOptions {
  pending: boolean;
  cameraMoved: boolean;
  hoverPointerButtons: number;
  dragging: boolean;
}

export interface ResolvedUsdHoverCameraMotion {
  pending: boolean;
  shouldMarkDirty: boolean;
  shouldSuppressProcessing: boolean;
}

export function resolveUsdHoverCameraMotion({
  pending,
  cameraMoved,
  hoverPointerButtons,
  dragging,
}: ResolveUsdHoverCameraMotionOptions): ResolvedUsdHoverCameraMotion {
  if (cameraMoved) {
    return {
      pending: true,
      shouldMarkDirty: false,
      shouldSuppressProcessing: true,
    };
  }

  if (pending && hoverPointerButtons === 0 && !dragging) {
    return {
      pending: false,
      shouldMarkDirty: true,
      shouldSuppressProcessing: false,
    };
  }

  return {
    pending,
    shouldMarkDirty: false,
    shouldSuppressProcessing: false,
  };
}

export function updateUsdHoverCameraMotionState(
  pendingRef: MutableValueRef<boolean>,
  options: Omit<ResolveUsdHoverCameraMotionOptions, 'pending'>,
): ResolvedUsdHoverCameraMotion {
  const nextState = resolveUsdHoverCameraMotion({
    pending: pendingRef.current,
    ...options,
  });
  pendingRef.current = nextState.pending;
  return nextState;
}
