import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { ImportPreparationOverlay } from './ImportPreparationOverlay.tsx';
import { VIEWER_CORNER_OVERLAY_CLASS_NAME } from '@/shared/components/3d/scene';

test('ImportPreparationOverlay keeps the workspace visible while folder imports prepare', () => {
  const markup = renderToStaticMarkup(
    React.createElement(ImportPreparationOverlay, {
      label: 'Preparing import…',
      detail: 'Scanning files',
    }),
  );

  assert.match(markup, /fixed inset-x-0 bottom-4/);
  assert.match(markup, /pointer-events-none/);
  assert.doesNotMatch(
    markup,
    /fixed inset-0 z-\[160\] flex items-center justify-center bg-black\/35/,
  );
});

test('ImportPreparationOverlay can share the viewer corner presentation', () => {
  const markup = renderToStaticMarkup(
    React.createElement(ImportPreparationOverlay, {
      label: 'Preparing import…',
      detail: 'Scanning files',
      placement: 'viewer-corner',
    }),
  );

  for (const className of VIEWER_CORNER_OVERLAY_CLASS_NAME.split(' ')) {
    assert.match(markup, new RegExp(className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.doesNotMatch(markup, /fixed inset-x-0 bottom-4/);
});
