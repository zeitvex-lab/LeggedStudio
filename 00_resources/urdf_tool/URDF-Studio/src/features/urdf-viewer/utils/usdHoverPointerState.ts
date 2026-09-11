export interface MutableValueRef<T> {
  current: T;
}

export interface UsdHoverPointerStateRefs {
  hoverPointerLocalRef: MutableValueRef<{ x: number; y: number } | null>;
  hoverPointerInsideRef: MutableValueRef<boolean>;
  hoverNeedsRaycastRef: MutableValueRef<boolean>;
  hoverPointerButtonsRef: MutableValueRef<number>;
}

export function markUsdHoverRaycastDirty(
  hoverNeedsRaycastRef: MutableValueRef<boolean>,
  requestFrame?: () => void,
): void {
  hoverNeedsRaycastRef.current = true;
  requestFrame?.();
}

export function setUsdHoverPointerState(
  refs: UsdHoverPointerStateRefs,
  pointer: { x: number; y: number },
  requestFrame?: () => void,
  buttons = refs.hoverPointerButtonsRef.current,
): void {
  refs.hoverPointerLocalRef.current = pointer;
  refs.hoverPointerInsideRef.current = true;
  refs.hoverNeedsRaycastRef.current = true;
  refs.hoverPointerButtonsRef.current = buttons;
  requestFrame?.();
}

export function setUsdHoverPointerButtons(
  hoverPointerButtonsRef: MutableValueRef<number>,
  buttons: number,
  requestFrame?: () => void,
): void {
  hoverPointerButtonsRef.current = buttons;
  requestFrame?.();
}

export function clearUsdHoverPointerState(
  refs: UsdHoverPointerStateRefs,
  requestFrame?: () => void,
): void {
  refs.hoverPointerInsideRef.current = false;
  refs.hoverPointerLocalRef.current = null;
  refs.hoverNeedsRaycastRef.current = false;
  refs.hoverPointerButtonsRef.current = 0;
  requestFrame?.();
}

export function shouldProcessUsdHoverRaycast(options: {
  hoverPointerInside: boolean;
  pointer: { x: number; y: number } | null;
  hoverNeedsRaycast: boolean;
  hoverPointerButtons: number;
  justSelected: boolean;
  dragging: boolean;
}): boolean {
  return options.hoverPointerInside
    && Boolean(options.pointer)
    && options.hoverNeedsRaycast
    && options.hoverPointerButtons === 0
    && !options.justSelected
    && !options.dragging;
}
