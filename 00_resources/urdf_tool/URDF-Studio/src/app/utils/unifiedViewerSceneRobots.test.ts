import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_LINK, type RobotState } from '@/types';

import { resolveUnifiedViewerEditorRobot } from './unifiedViewerSceneRobots.ts';

function createRobotState(name: string, rootLinkId: string): RobotState {
  return {
    name,
    rootLinkId,
    selection: { type: null, id: null },
    links: {
      [rootLinkId]: {
        ...DEFAULT_LINK,
        id: rootLinkId,
        name: rootLinkId,
      },
    },
    joints: {},
  };
}

test('resolveUnifiedViewerEditorRobot keeps the live robot outside assembly workspace mode', () => {
  const robot = createRobotState('merged-assembly', 'merged_root');
  const viewerRobot = createRobotState('workspace-display', '__workspace_world__');

  assert.equal(
    resolveUnifiedViewerEditorRobot({
      robot,
      viewerRobot,
      assemblyWorkspaceActive: false,
    }),
    robot,
  );
});

test('resolveUnifiedViewerEditorRobot uses the stable workspace display robot in assembly workspace mode', () => {
  const robot = createRobotState('merged-assembly', 'merged_root');
  const viewerRobot = createRobotState('workspace-display', '__workspace_world__');

  assert.equal(
    resolveUnifiedViewerEditorRobot({
      robot,
      viewerRobot,
      assemblyWorkspaceActive: true,
    }),
    viewerRobot,
  );
});
