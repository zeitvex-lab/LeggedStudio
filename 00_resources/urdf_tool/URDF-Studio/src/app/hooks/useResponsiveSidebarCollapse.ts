import { useEffect, useRef } from 'react';

interface SidebarCollapseState {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
}

type SetSidebarCollapsed = (side: 'left' | 'right', collapsed: boolean) => void;

interface UseResponsiveSidebarCollapseParams {
  sidebar: SidebarCollapseState;
  setSidebar: SetSidebarCollapsed;
}

const COMPACT_WORKSPACE_WIDTH = 1024;
const MEDIUM_WORKSPACE_WIDTH = 1200;

export function useResponsiveSidebarCollapse({
  sidebar,
  setSidebar,
}: UseResponsiveSidebarCollapseParams) {
  const initialSidebarRef = useRef(sidebar);

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      const currentSidebar = initialSidebarRef.current;

      if (width < COMPACT_WORKSPACE_WIDTH) {
        if (!currentSidebar.leftCollapsed) setSidebar('left', true);
        if (!currentSidebar.rightCollapsed) setSidebar('right', true);
      } else if (width < MEDIUM_WORKSPACE_WIDTH) {
        if (!currentSidebar.rightCollapsed) setSidebar('right', true);
      }
    };

    handleResize();

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [setSidebar]);
}
