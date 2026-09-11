import type { MouseEvent as ReactMouseEvent } from 'react';
import type { RobotFile } from '@/types';
import type { FileTreeNode } from '../utils';
import { TreeEditorFileBrowserContent } from './TreeEditorFileBrowserContent';
import type { TreeEditorTranslations } from './treeEditorTypes';

interface TreeEditorFileBrowserSectionProps {
  availableFiles: RobotFile[];
  editingFolderPath?: string | null;
  expandedFolders: Set<string>;
  fileBrowserHeight: number;
  fileTree: FileTreeNode[];
  folderRenameDraft?: string;
  folderRenameInputRef?: React.RefObject<HTMLInputElement | null>;
  isDragging: boolean;
  isFileBrowserOpen: boolean;
  isProMode: boolean;
  isStructureOpen: boolean;
  onAddComponent?: (file: RobotFile) => void;
  onCancelFolderRename?: () => void;
  onCommitFolderRename?: () => void;
  onFileContextMenu: (event: ReactMouseEvent, file: RobotFile) => void;
  onFileLoad?: (file: RobotFile) => void;
  onFolderRenameDraftChange?: (value: string) => void;
  onFolderContextMenu: (event: ReactMouseEvent, folderPath: string) => void;
  onResizeMouseDown: (event: ReactMouseEvent) => void;
  onToggleOpen: () => void;
  shouldFillSpace: boolean;
  t: TreeEditorTranslations;
  toggleFolder: (path: string) => void;
}

export function TreeEditorFileBrowserSection({
  availableFiles,
  editingFolderPath,
  expandedFolders,
  fileBrowserHeight,
  fileTree,
  folderRenameDraft = '',
  folderRenameInputRef,
  isDragging,
  isFileBrowserOpen,
  isProMode,
  isStructureOpen,
  onAddComponent,
  onCancelFolderRename = () => {},
  onCommitFolderRename = () => {},
  onFileContextMenu,
  onFileLoad,
  onFolderRenameDraftChange = () => {},
  onFolderContextMenu,
  onResizeMouseDown,
  onToggleOpen,
  shouldFillSpace,
  t,
  toggleFolder,
}: TreeEditorFileBrowserSectionProps) {
  return (
    <>
      <TreeEditorFileBrowserContent
        availableFiles={availableFiles}
        editingFolderPath={editingFolderPath}
        expandedFolders={expandedFolders}
        fileTree={fileTree}
        folderRenameDraft={folderRenameDraft}
        folderRenameInputRef={folderRenameInputRef ?? { current: null }}
        height={fileBrowserHeight}
        isDragging={isDragging}
        isOpen={isFileBrowserOpen}
        showAddAsComponent={isProMode}
        onAddComponent={onAddComponent}
        onCancelFolderRename={onCancelFolderRename}
        onCommitFolderRename={onCommitFolderRename}
        onLoadRobot={onFileLoad}
        onFileContextMenu={onFileContextMenu}
        onFolderRenameDraftChange={onFolderRenameDraftChange}
        onFolderContextMenu={onFolderContextMenu}
        onToggleOpen={onToggleOpen}
        shouldFillSpace={shouldFillSpace}
        t={t}
        toggleFolder={toggleFolder}
      />

      {isFileBrowserOpen && isStructureOpen && (
        <button
          type="button"
          className="h-1 bg-border-black cursor-row-resize hover:bg-system-blue transition-colors shrink-0 z-10"
          aria-label={t.resize}
          onMouseDown={onResizeMouseDown}
        />
      )}
    </>
  );
}
