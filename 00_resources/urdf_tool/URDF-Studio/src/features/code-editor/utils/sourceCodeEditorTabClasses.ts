const SOURCE_CODE_EDITOR_TAB_BASE_CLASS =
  'group relative flex h-full shrink-0 items-center gap-1.5 border-r border-border-black px-3 text-[11px] font-medium tracking-[0.01em] transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-system-blue/40';

export const SOURCE_CODE_EDITOR_INLINE_TAB_LIMIT = 4;

// VS Code-style flat tab strip: tabs sit flush against the editor, no outer
// "segmented" capsule. The host only lays the tabs out edge to edge; the bar
// border + background live on the wrapper in SourceCodeEditor.
export const SOURCE_CODE_EDITOR_TABS_CLASS = 'flex h-full min-w-max items-stretch';

export const shouldCollapseSourceCodeEditorTabs = (documentCount: number): boolean =>
  documentCount > SOURCE_CODE_EDITOR_INLINE_TAB_LIMIT;

export const getSourceCodeEditorTabClassName = (isActive: boolean): string =>
  `${SOURCE_CODE_EDITOR_TAB_BASE_CLASS} ${
    isActive
      ? 'bg-panel-bg text-text-primary'
      : 'bg-element-bg text-text-secondary hover:bg-element-hover hover:text-text-primary'
  }`;

// Top accent line that connects the active tab to the editor below, the way
// VS Code highlights the focused editor tab.
export const getSourceCodeEditorTabAccentClassName = (isActive: boolean): string =>
  `pointer-events-none absolute inset-x-0 top-0 h-0.5 transition-colors ${
    isActive ? 'bg-system-blue' : 'bg-transparent group-hover:bg-border-black'
  }`;

export const getSourceCodeEditorTabBadgeClassName = (isActive: boolean): string =>
  `ml-1 shrink-0 rounded px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wide transition-colors ${
    isActive
      ? 'bg-system-blue/10 text-system-blue'
      : 'bg-element-hover text-text-secondary group-hover:bg-system-blue/10 group-hover:text-system-blue'
  }`;
