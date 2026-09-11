import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { translations } from '@/shared/i18n';
import { TreeEditorFileBrowserContent } from './TreeEditorFileBrowserContent';

test('asset library empty state centers without adding scroll height', () => {
  const markup = renderToStaticMarkup(
    <TreeEditorFileBrowserContent
      availableFiles={[]}
      expandedFolders={new Set()}
      fileTree={[]}
      folderRenameDraft=""
      folderRenameInputRef={React.createRef<HTMLInputElement>()}
      height={180}
      isDragging={false}
      isOpen
      showAddAsComponent={false}
      onCancelFolderRename={() => {}}
      onCommitFolderRename={() => {}}
      onFileContextMenu={() => {}}
      onFolderRenameDraftChange={() => {}}
      onFolderContextMenu={() => {}}
      onToggleOpen={() => {}}
      shouldFillSpace
      t={translations.en}
      toggleFolder={() => {}}
    />,
  );

  assert.match(markup, /Drop or import files/);
  assert.match(markup, /min-h-full/);
  assert.doesNotMatch(markup, /py-4/);
});
