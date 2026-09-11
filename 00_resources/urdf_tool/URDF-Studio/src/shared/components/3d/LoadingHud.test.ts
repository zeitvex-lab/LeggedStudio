import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { LoadingHud } from './LoadingHud.tsx';

test('LoadingHud renders a true indeterminate bar without fake partial width', () => {
  const markup = renderToStaticMarkup(
    React.createElement(LoadingHud, {
      title: 'Loading robot',
      detail: 'Preparing scene…',
      progress: null,
      progressMode: 'indeterminate',
      delayMs: 0,
    }),
  );

  assert.doesNotMatch(markup, /width:38%/);
  assert.match(markup, /animate-pulse/);
  assert.match(markup, /w-full/);
});

test('LoadingHud shrinks to the available overlay safe area', () => {
  const markup = renderToStaticMarkup(
    React.createElement(LoadingHud, {
      title: 'Loading robot',
      detail: 'Preparing scene…',
      progress: 0.25,
      delayMs: 0,
    }),
  );

  assert.match(markup, /min-w-0/);
  assert.doesNotMatch(markup, /min-w-\[220px\]/);
  assert.match(markup, /max-width:100%/);
  assert.match(markup, /width:min\(280px,\s*100%\)/);
});
