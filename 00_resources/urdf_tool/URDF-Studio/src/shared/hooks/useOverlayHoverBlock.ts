import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';

interface OverlayHoverBlockActions {
  beginHoverBlock: () => void;
  endHoverBlock: () => void;
  clearHover: () => void;
}

interface OverlayHoverBlockProviderProps {
  value: OverlayHoverBlockActions;
  children: ReactNode;
}

const noopOverlayHoverBlockActions: OverlayHoverBlockActions = {
  beginHoverBlock: () => {},
  endHoverBlock: () => {},
  clearHover: () => {},
};

const OverlayHoverBlockContext = createContext<OverlayHoverBlockActions>(
  noopOverlayHoverBlockActions,
);

export function OverlayHoverBlockProvider({ value, children }: OverlayHoverBlockProviderProps) {
  const contextValue = useMemo(
    () => ({
      beginHoverBlock: value.beginHoverBlock,
      endHoverBlock: value.endHoverBlock,
      clearHover: value.clearHover,
    }),
    [value.beginHoverBlock, value.clearHover, value.endHoverBlock],
  );

  return createElement(OverlayHoverBlockContext.Provider, { value: contextValue }, children);
}

export function useOverlayHoverBlock() {
  const { beginHoverBlock, endHoverBlock, clearHover } = useContext(OverlayHoverBlockContext);
  const blockActiveRef = useRef(false);

  const activateHoverBlock = useCallback(() => {
    if (blockActiveRef.current) {
      return;
    }

    blockActiveRef.current = true;
    beginHoverBlock();
    clearHover();
  }, [beginHoverBlock, clearHover]);

  const deactivateHoverBlock = useCallback(() => {
    if (!blockActiveRef.current) {
      return;
    }

    blockActiveRef.current = false;
    endHoverBlock();
  }, [endHoverBlock]);

  useEffect(() => {
    return () => {
      if (!blockActiveRef.current) {
        return;
      }

      blockActiveRef.current = false;
      endHoverBlock();
    };
  }, [endHoverBlock]);

  return {
    activateHoverBlock,
    deactivateHoverBlock,
  };
}
