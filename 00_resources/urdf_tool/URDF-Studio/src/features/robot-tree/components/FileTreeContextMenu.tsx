import React from 'react';
import { Download, Edit3, Plus, Trash2 } from 'lucide-react';
import { ContextMenuFrame, ContextMenuItem } from '@/shared/components/ui';

export interface FileTreeContextMenuProps {
  position: { x: number; y: number } | null;
  addLabel?: string;
  renameLabel?: string;
  exportLabel?: string;
  deleteLabel?: string;
  onAdd?: () => void;
  onRename?: () => void;
  onExport?: () => void;
  onDelete?: () => void;
  showAddAction?: boolean;
  showRenameAction?: boolean;
  showExportAction?: boolean;
  showDeleteAction?: boolean;
}

export const FileTreeContextMenu: React.FC<FileTreeContextMenuProps> = ({
  position,
  addLabel,
  renameLabel,
  exportLabel,
  deleteLabel,
  onAdd,
  onRename,
  onExport,
  onDelete,
  showAddAction = true,
  showRenameAction = false,
  showExportAction = false,
  showDeleteAction = false,
}) => {
  if (!position) return null;
  if (!showAddAction && !showRenameAction && !showExportAction && !showDeleteAction) {
    return null;
  }

  return (
    <ContextMenuFrame position={position} widthClassName="w-44">
      {showAddAction && addLabel && onAdd && (
        <ContextMenuItem onClick={onAdd} icon={<Plus size={12} />}>
          {addLabel}
        </ContextMenuItem>
      )}
      {showRenameAction && renameLabel && onRename && (
        <ContextMenuItem onClick={onRename} icon={<Edit3 size={12} />}>
          {renameLabel}
        </ContextMenuItem>
      )}
      {showExportAction && exportLabel && onExport && (
        <ContextMenuItem onClick={onExport} icon={<Download size={12} />}>
          {exportLabel}
        </ContextMenuItem>
      )}
      {showDeleteAction && deleteLabel && onDelete && (
        <ContextMenuItem onClick={onDelete} icon={<Trash2 size={12} />} tone="danger">
          {deleteLabel}
        </ContextMenuItem>
      )}
    </ContextMenuFrame>
  );
};
