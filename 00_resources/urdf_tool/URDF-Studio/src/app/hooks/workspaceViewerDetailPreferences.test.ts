import test from 'node:test';
import assert from 'node:assert/strict';

import { JSDOM } from 'jsdom';

import { DEFAULT_LINK } from '@/types';
import {
  WORKSPACE_VIEWER_SHOW_VISUAL_STORAGE_KEY,
  persistWorkspaceViewerShowVisualPreference,
  readStoredWorkspaceViewerShowVisualPreference,
  resolveWorkspaceViewerShowVisual,
} from './workspaceViewerDetailPreferences.ts';

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  Object.defineProperty(globalThis, 'localStorage', {
    value: dom.window.localStorage,
    configurable: true,
  });

  return dom;
}

test('workspace viewer show-visual preference round-trips through local storage', () => {
  const dom = installDom();

  assert.equal(readStoredWorkspaceViewerShowVisualPreference(), null);

  persistWorkspaceViewerShowVisualPreference(false);

  assert.equal(dom.window.localStorage.getItem(WORKSPACE_VIEWER_SHOW_VISUAL_STORAGE_KEY), 'false');
  assert.equal(readStoredWorkspaceViewerShowVisualPreference(), false);

  persistWorkspaceViewerShowVisualPreference(true);

  assert.equal(dom.window.localStorage.getItem(WORKSPACE_VIEWER_SHOW_VISUAL_STORAGE_KEY), 'true');
  assert.equal(readStoredWorkspaceViewerShowVisualPreference(), true);

  dom.window.close();
});

test('workspace viewer show-visual preference can suppress visible links on restore', () => {
  const visibleLinks = {
    base_link: {
      ...DEFAULT_LINK,
      id: 'base_link',
      name: 'base_link',
      visible: true,
    },
  };

  assert.equal(
    resolveWorkspaceViewerShowVisual({
      robotLinks: visibleLinks,
      storedPreference: false,
    }),
    false,
  );
  assert.equal(
    resolveWorkspaceViewerShowVisual({
      robotLinks: visibleLinks,
      storedPreference: true,
    }),
    true,
  );
});

test('workspace viewer show-visual restore still respects robots with no visible links', () => {
  const hiddenLinks = {
    base_link: {
      ...DEFAULT_LINK,
      id: 'base_link',
      name: 'base_link',
      visible: false,
    },
  };

  assert.equal(
    resolveWorkspaceViewerShowVisual({
      robotLinks: hiddenLinks,
      storedPreference: true,
    }),
    false,
  );
});
