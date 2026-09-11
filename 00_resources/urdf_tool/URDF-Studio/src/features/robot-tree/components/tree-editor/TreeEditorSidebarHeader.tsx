import { ChevronLeft, ChevronRight } from 'lucide-react';

interface TreeEditorSidebarHeaderProps {
  collapsed?: boolean;
  onToggle?: () => void;
  collapseTitle: string;
  expandTitle: string;
}

export function TreeEditorSidebarHeader({
  collapsed,
  onToggle,
  collapseTitle,
  expandTitle,
}: TreeEditorSidebarHeaderProps) {
  return (
    <button
      onClick={onToggle}
      className="absolute -right-4 top-1/2 -translate-y-1/2 w-4 h-16 bg-panel-bg hover:bg-system-blue-solid hover:text-white border border-border-strong rounded-r-lg shadow-md flex flex-col items-center justify-center z-50 cursor-pointer text-text-tertiary transition-all group"
      title={collapsed ? expandTitle : collapseTitle}
    >
      <div className="flex flex-col gap-0.5 items-center">
        <div className="w-1 h-1 rounded-full bg-text-tertiary/40 group-hover:bg-white/80" />
        {collapsed ? (
          <ChevronRight className="w-3.5 h-3.5" />
        ) : (
          <ChevronLeft className="w-3.5 h-3.5" />
        )}
        <div className="w-1 h-1 rounded-full bg-text-tertiary/40 group-hover:bg-white/80" />
      </div>
    </button>
  );
}
