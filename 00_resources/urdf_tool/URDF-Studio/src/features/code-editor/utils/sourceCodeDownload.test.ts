import assert from 'node:assert/strict';
import test from 'node:test';

import { JSDOM } from 'jsdom';

import { downloadSourceCodeDocument } from './sourceCodeDownload';

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  (globalThis as { URL?: typeof URL }).URL = dom.window.URL as unknown as typeof URL;
  (globalThis as { HTMLAnchorElement?: typeof HTMLAnchorElement }).HTMLAnchorElement = dom.window.HTMLAnchorElement;
  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;

  return dom;
}

test('downloadSourceCodeDocument triggers browser download and emits completion callback', () => {
  const dom = installDom();
  const originalCreateObjectUrl = URL.createObjectURL;
  const originalRevokeObjectUrl = URL.revokeObjectURL;
  const originalAnchorClick = HTMLAnchorElement.prototype.click;
  let revokeArg: string | null = null as string | null;
  let anchorClickCount = 0;
  let completionCount = 0;

  URL.createObjectURL = (() => 'blob:mock-source-download') as typeof URL.createObjectURL;
  URL.revokeObjectURL = ((url: string) => {
    revokeArg = url;
  }) as typeof URL.revokeObjectURL;
  HTMLAnchorElement.prototype.click = function click() {
    anchorClickCount += 1;
  };

  try {
    const didDownload = downloadSourceCodeDocument({
      content: '<robot name="demo" />',
      fileName: 'demo.urdf',
      documentFlavor: 'urdf',
      onDownload: () => {
        completionCount += 1;
      },
    });

    assert.equal(didDownload, true);
    assert.equal(anchorClickCount, 1);
    assert.equal(revokeArg, 'blob:mock-source-download');
    assert.equal(completionCount, 1);
    assert.equal(document.body.childElementCount, 0, 'temporary anchor should be cleaned up');
  } finally {
    URL.createObjectURL = originalCreateObjectUrl;
    URL.revokeObjectURL = originalRevokeObjectUrl;
    HTMLAnchorElement.prototype.click = originalAnchorClick;
    dom.window.close();
  }
});

test('downloadSourceCodeDocument ignores equivalent MJCF preview downloads', () => {
  const dom = installDom();
  let completionCount = 0;

  try {
    const didDownload = downloadSourceCodeDocument({
      content: '<mujoco model="demo" />',
      fileName: 'demo.equivalent.mjcf',
      documentFlavor: 'equivalent-mjcf',
      onDownload: () => {
        completionCount += 1;
      },
    });

    assert.equal(didDownload, false);
    assert.equal(completionCount, 0);
  } finally {
    dom.window.close();
  }
});
