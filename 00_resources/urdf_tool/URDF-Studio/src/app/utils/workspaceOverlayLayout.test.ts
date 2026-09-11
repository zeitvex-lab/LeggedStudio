import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveWorkspaceOverlayLayoutClassNames } from './workspaceOverlayLayout';
import {
  VIEWER_CORNER_OVERLAY_CLASS_NAME,
  resolveWorkspaceOverlayGizmoMargin,
  resolveWorkspaceOverlaySafeAreaStyle,
} from '@/shared/components/3d/scene';

test('workspace overlay layout keeps the viewer independent from sidebar width', () => {
  const classes = resolveWorkspaceOverlayLayoutClassNames();

  assert.match(classes.root, /\brelative\b/);
  assert.match(classes.root, /\boverflow-hidden\b/);
  assert.match(classes.viewerLayer, /\babsolute\b/);
  assert.match(classes.viewerLayer, /\binset-0\b/);
  assert.match(classes.leftSidebarLayer, /\babsolute\b/);
  assert.match(classes.leftSidebarLayer, /\bleft-0\b/);
  assert.match(classes.rightSidebarLayer, /\babsolute\b/);
  assert.match(classes.rightSidebarLayer, /\bright-0\b/);
  assert.match(classes.rightSidebarLayer, /\bpointer-events-none\b/);
});

test('workspace overlay safe area exposes visible sidebar widths as CSS variables', () => {
  assert.deepEqual(
    resolveWorkspaceOverlaySafeAreaStyle({
      leftCollapsed: false,
      propertyEditorWidth: 310,
      rightCollapsed: false,
      treeSidebarWidth: 264,
    }),
    {
      '--workspace-overlay-left-inset': '264px',
      '--workspace-overlay-right-inset': '310px',
    },
  );

  assert.deepEqual(
    resolveWorkspaceOverlaySafeAreaStyle({
      leftCollapsed: true,
      propertyEditorWidth: 310,
      rightCollapsed: true,
      treeSidebarWidth: 264,
    }),
    {
      '--workspace-overlay-left-inset': '0px',
      '--workspace-overlay-right-inset': '0px',
    },
  );
});

test('viewer corner overlay clips and shrinks HUDs inside the safe area', () => {
  assert.match(VIEWER_CORNER_OVERLAY_CLASS_NAME, /\bbox-border\b/);
  assert.match(VIEWER_CORNER_OVERLAY_CLASS_NAME, /\bmin-w-0\b/);
  assert.match(VIEWER_CORNER_OVERLAY_CLASS_NAME, /\boverflow-hidden\b/);
  assert.match(
    VIEWER_CORNER_OVERLAY_CLASS_NAME,
    /var\(--workspace-overlay-left-inset,0px\)\+1rem/,
  );
  assert.match(
    VIEWER_CORNER_OVERLAY_CLASS_NAME,
    /var\(--workspace-overlay-right-inset,0px\)\+1rem/,
  );
});

test('workspace overlay gizmo margin clears the expanded right sidebar', () => {
  assert.deepEqual(
    resolveWorkspaceOverlayGizmoMargin({
      leftCollapsed: false,
      propertyEditorWidth: 310,
      rightCollapsed: false,
      treeSidebarWidth: 264,
    }),
    [378, 68],
  );

  assert.deepEqual(
    resolveWorkspaceOverlayGizmoMargin({
      leftCollapsed: false,
      propertyEditorWidth: 310,
      rightCollapsed: true,
      treeSidebarWidth: 264,
    }),
    [68, 68],
  );
});
