import assert from 'node:assert/strict';
import test from 'node:test';

import type { ComponentSourceDraft, RobotFile } from '@/types';
import { useAssetsStore } from './assetsStore.ts';

const template: RobotFile = {
  name: 'library/shared.xml',
  format: 'mjcf',
  content: '<mujoco model="template"/>',
};

function draft(componentId: string, content: string): ComponentSourceDraft {
  return {
    componentId,
    format: 'mjcf',
    content,
    robotSnapshotHash: `robot-semantic-v1:fixture:${componentId}`,
  };
}

test('component drafts isolate instances sharing one immutable library source', () => {
  useAssetsStore.setState({
    availableFiles: [structuredClone(template)],
    allFileContents: { [template.name]: template.content },
    componentSourceDrafts: {},
  });

  const store = useAssetsStore.getState();
  store.setComponentSourceDraft(draft('left', '<mujoco model="left"/>'));
  store.setComponentSourceDraft(draft('right', '<mujoco model="right"/>'));

  const state = useAssetsStore.getState();
  assert.equal(state.componentSourceDrafts.left.content, '<mujoco model="left"/>');
  assert.equal(state.componentSourceDrafts.right.content, '<mujoco model="right"/>');
  assert.equal(state.availableFiles[0].content, template.content);
  assert.equal(state.allFileContents[template.name], template.content);

  state.removeComponentSourceDraft('left');
  assert.equal(useAssetsStore.getState().componentSourceDrafts.left, undefined);
  assert.equal(useAssetsStore.getState().componentSourceDrafts.right.content, '<mujoco model="right"/>');
});

test('workspace replacement pruning cannot retain drafts owned by removed components', () => {
  useAssetsStore.setState({
    componentSourceDrafts: {
      left: draft('left', '<mujoco model="left"/>'),
      right: draft('right', '<mujoco model="right"/>'),
      removed: draft('removed', '<mujoco model="removed"/>'),
    },
  });
  useAssetsStore.getState().pruneComponentSourceDrafts(['left', 'right']);
  assert.deepEqual(Object.keys(useAssetsStore.getState().componentSourceDrafts).sort(), [
    'left',
    'right',
  ]);
});
