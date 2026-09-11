import assert from 'node:assert/strict';
import test from 'node:test';

import { createSingleComponentWorkspace } from '@/core/robot';
import { useSelectionStore } from '@/store/selectionStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  JointType,
  type RobotState,
} from '@/types';

import {
  createConversationLaunchContext,
  resolveCurrentAIConversationSelection,
} from './aiConversationLaunch.ts';

function createRobotSnapshot(): RobotState {
  return {
    name: 'Test robot',
    links: {
      base_link: {
        ...structuredClone(DEFAULT_LINK),
        id: 'base_link',
        name: 'base_link',
      },
      tool_link: {
        ...structuredClone(DEFAULT_LINK),
        id: 'tool_link',
        name: 'tool_link',
      },
    },
    joints: {
      shoulder: {
        ...structuredClone(DEFAULT_JOINT),
        id: 'shoulder',
        name: 'shoulder',
        type: JointType.REVOLUTE,
        parentLinkId: 'base_link',
        childLinkId: 'tool_link',
      },
    },
    rootLinkId: 'base_link',
    selection: { type: null, id: null },
  };
}

function seedWorkspaceSelection(type: 'link' | 'joint', entityId: string) {
  const robot = createRobotSnapshot();
  const { selection: _selection, ...robotData } = robot;
  useWorkspaceStore.setState({
    workspace: createSingleComponentWorkspace(robotData, { componentId: 'arm' }),
    activeComponentId: 'arm',
  });
  useSelectionStore.getState().setSelection({
    entity: { type, componentId: 'arm', entityId },
  });
}

test('current AI conversation selection retains explicit component ownership', () => {
  seedWorkspaceSelection('joint', 'shoulder');

  assert.deepEqual(resolveCurrentAIConversationSelection(), {
    type: 'joint',
    componentId: 'arm',
    entityId: 'shoulder',
    snapshotEntityId: 'shoulder',
  });
});

test('createConversationLaunchContext clones payloads and derives canonical selection', () => {
  seedWorkspaceSelection('joint', 'shoulder');
  const robotSnapshot = createRobotSnapshot();
  const inspectionReportSnapshot = {
    summary: 'Needs review',
    overallScore: 72,
    issues: [
      {
        type: 'warning' as const,
        title: 'Joint range',
        description: 'Joint range may be narrow.',
        profileId: 'base.kinematics',
        itemId: 'joint_range',
      },
    ],
  };

  const launchContext = createConversationLaunchContext({
    sessionId: 4,
    mode: 'inspection-followup',
    robotSnapshot,
    inspectionReportSnapshot,
    focusedIssue: inspectionReportSnapshot.issues[0],
  });

  robotSnapshot.name = 'mutated';
  inspectionReportSnapshot.issues[0].title = 'Mutated issue';

  assert.equal(launchContext.robotSnapshot.name, 'Test robot');
  assert.deepEqual(launchContext.selectedEntity, {
    type: 'joint',
    componentId: 'arm',
    entityId: 'shoulder',
    snapshotEntityId: 'shoulder',
  });
  assert.equal(launchContext.inspectionReportSnapshot?.issues[0]?.title, 'Joint range');
});

test('explicit null selection does not inherit an unrelated live workspace selection', () => {
  seedWorkspaceSelection('joint', 'shoulder');

  const launchContext = createConversationLaunchContext({
    sessionId: 7,
    mode: 'general',
    robotSnapshot: createRobotSnapshot(),
    selectedEntity: null,
  });

  assert.equal(launchContext.selectedEntity, null);
});
