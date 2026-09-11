import { useCallback, useEffect } from 'react';
import { useUIStore, type ManagedWindowId } from './uiStore';

export function useManagedWindowLayer(windowId: ManagedWindowId) {
  const zIndex = useUIStore((state) => state.getManagedWindowZIndex(windowId));
  const bringWindowToFront = useUIStore((state) => state.bringWindowToFront);

  // A managed window mounts only while it is open — every consumer is rendered
  // behind `{isOpen && <Component/>}`. Bringing it to the front on mount makes
  // "the most recently opened window sits on top" hold without each call site
  // having to remember to call `onActivate` imperatively. `bringWindowToFront`
  // is a no-op when the window is already at the front, so this is safe for
  // long-lived consumers (e.g. viewer panels) that mount once.
  useEffect(() => {
    bringWindowToFront(windowId);
  }, [bringWindowToFront, windowId]);

  const onActivate = useCallback(() => {
    bringWindowToFront(windowId);
  }, [bringWindowToFront, windowId]);

  return { zIndex, onActivate };
}
