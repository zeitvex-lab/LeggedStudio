import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { UsageGuide } from './UsageGuide';

test('usage guide clears the narrow-screen bottom toolbar and keeps wide-screen placement', () => {
  const markup = renderToStaticMarkup(<UsageGuide lang="en" />);

  assert.match(markup, /bottom-\[calc\(4\.25rem\+env\(safe-area-inset-bottom\)\)\]/);
  assert.match(markup, /sm:bottom-4/);
});
