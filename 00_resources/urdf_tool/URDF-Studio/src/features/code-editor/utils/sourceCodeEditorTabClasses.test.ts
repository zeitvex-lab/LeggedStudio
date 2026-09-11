import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getSourceCodeEditorTabAccentClassName,
  getSourceCodeEditorTabBadgeClassName,
  getSourceCodeEditorTabClassName,
  shouldCollapseSourceCodeEditorTabs,
  SOURCE_CODE_EDITOR_INLINE_TAB_LIMIT,
  SOURCE_CODE_EDITOR_TABS_CLASS,
} from './sourceCodeEditorTabClasses.ts';

test('source code editor tabs use a flat VS Code-style strip without a capsule host', () => {
  assert.match(SOURCE_CODE_EDITOR_TABS_CLASS, /\bitems-stretch\b/);
  assert.match(SOURCE_CODE_EDITOR_TABS_CLASS, /\bmin-w-max\b/);
  assert.doesNotMatch(SOURCE_CODE_EDITOR_TABS_CLASS, /\bbg-segmented-bg\b/);
  assert.doesNotMatch(SOURCE_CODE_EDITOR_TABS_CLASS, /rounded-\[10px\]/);
});

test('active source code editor tab connects to the editor surface', () => {
  const className = getSourceCodeEditorTabClassName(true);

  assert.match(className, /\bbg-panel-bg\b/);
  assert.match(className, /\btext-text-primary\b/);
});

test('active source code editor tab shows the blue accent line', () => {
  assert.match(getSourceCodeEditorTabAccentClassName(true), /\bbg-system-blue\b/);
  assert.match(getSourceCodeEditorTabAccentClassName(false), /\bbg-transparent\b/);
});

test('inactive source code editor tab exposes a visible hover state', () => {
  const className = getSourceCodeEditorTabClassName(false);

  assert.match(className, /\bbg-element-bg\b/);
  assert.match(className, /\bhover:bg-element-hover\b/);
  assert.match(className, /\bhover:text-text-primary\b/);
});

test('generated badge follows the tab selection state', () => {
  assert.match(getSourceCodeEditorTabBadgeClassName(true), /\bbg-system-blue\/10\b/);
  assert.match(getSourceCodeEditorTabBadgeClassName(false), /\bgroup-hover:bg-system-blue\/10\b/);
});

test('source code editor collapses many document tabs into a selector', () => {
  assert.equal(shouldCollapseSourceCodeEditorTabs(SOURCE_CODE_EDITOR_INLINE_TAB_LIMIT), false);
  assert.equal(shouldCollapseSourceCodeEditorTabs(SOURCE_CODE_EDITOR_INLINE_TAB_LIMIT + 1), true);
});
