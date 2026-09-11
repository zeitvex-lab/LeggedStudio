import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { ViewMenuItem } from './ViewMenuItem.tsx';

test('ViewMenuItem renders a disabled toggle when the target panel is unavailable', () => {
  const markup = renderToStaticMarkup(
    React.createElement(ViewMenuItem, {
      checked: false,
      disabled: true,
      label: 'Joints Panel',
      onClick: () => {},
    }),
  );

  assert.match(markup, /disabled=""/);
  assert.match(markup, /Joints Panel/);
});
