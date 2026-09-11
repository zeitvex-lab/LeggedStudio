import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { JSDOM } from 'jsdom';

import { AppErrorBoundary } from './AppErrorBoundary.tsx';

function renderErrorBoundaryForLanguage(
  dataLang: 'en' | 'zh',
  error: unknown = new Error('render failed'),
) {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
  });
  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  document.documentElement.dataset.lang = dataLang;

  try {
    const boundary = new AppErrorBoundary({ children: null });
    boundary.state = { hasError: true, error };
    const node = boundary.render();
    assert.ok(React.isValidElement(node), 'boundary should render an element after an error');
    return renderToStaticMarkup(node);
  } finally {
    dom.window.close();
  }
}

test('AppErrorBoundary renders English copy without mixed Chinese UI', () => {
  const markup = renderErrorBoundaryForLanguage('en');

  assert.match(markup, /Something went wrong/);
  assert.match(markup, /Rendering was interrupted/);
  assert.match(markup, />Reload</);
  assert.doesNotMatch(markup, /应用遇到错误/);
  assert.doesNotMatch(markup, /重新加载/);
});

test('AppErrorBoundary renders Chinese copy without mixed English UI', () => {
  const markup = renderErrorBoundaryForLanguage('zh');

  assert.match(markup, /应用遇到错误/);
  assert.match(markup, /页面渲染中断/);
  assert.match(markup, />重新加载</);
  assert.doesNotMatch(markup, /Something went wrong/);
  assert.doesNotMatch(markup, />Reload</);
});

test('AppErrorBoundary renders falsy thrown values without crashing', () => {
  const markup = renderErrorBoundaryForLanguage('en', null);

  assert.match(markup, /Something went wrong/);
  assert.match(markup, />null</);
});
