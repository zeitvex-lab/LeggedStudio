import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { FileDropOverlay } from './FileDropOverlay.tsx';

test('FileDropOverlay uses a downward import icon for the drag-import hover state', () => {
  const markup = renderToStaticMarkup(
    React.createElement(FileDropOverlay, {
      visible: true,
      title: 'Drop files to import',
      hint: 'Import the full folder or archive.',
    }),
  );

  assert.match(markup, /lucide-import/, 'drag-import hover should use the import icon');
  assert.doesNotMatch(markup, /lucide-upload/, 'drag-import hover should not show an upload arrow');
});
