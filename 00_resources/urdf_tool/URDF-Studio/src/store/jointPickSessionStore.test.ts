import assert from 'node:assert/strict';
import test from 'node:test';

import { useJointPickSessionStore, type PickedSnapFrame } from './jointPickSessionStore.ts';

function makeFrame(side: 'parent' | 'child'): PickedSnapFrame {
  return {
    side,
    componentId: `comp_${side}`,
    linkId: 'base_link',
    kind: 'faceCenter',
    pointWorld: { x: 1, y: 2, z: 3 },
    poseWorldMatrix: new Array(16).fill(0),
    linkWorldMatrix: new Array(16).fill(0),
  };
}

test('jointPickSessionStore startPick activates the session for a side and clears pending', () => {
  const store = useJointPickSessionStore;
  store.getState().reset();
  store.getState().pushPending({
    componentId: 'c',
    linkId: 'l',
    linkWorldMatrix: new Array(16).fill(0),
    point: { x: 0, y: 0, z: 0 },
  });

  store.getState().startPick('child');
  assert.equal(store.getState().active, true);
  assert.equal(store.getState().side, 'child');
  assert.equal(store.getState().pending.length, 0);

  store.getState().reset();
});

test('jointPickSessionStore commitSnap stores by side and clears pending', () => {
  const store = useJointPickSessionStore;
  store.getState().reset();

  store.getState().commitSnap(makeFrame('parent'));
  assert.equal(store.getState().parentSnap?.componentId, 'comp_parent');
  assert.equal(store.getState().parentComponentId, 'comp_parent');
  assert.equal(store.getState().parentLinkId, 'base_link');
  assert.equal(store.getState().childSnap, null);
  assert.equal(store.getState().side, 'child');

  store.getState().commitSnap(makeFrame('child'));
  assert.equal(store.getState().childSnap?.componentId, 'comp_child');
  assert.equal(store.getState().childComponentId, 'comp_child');
  assert.equal(store.getState().childLinkId, 'base_link');
  assert.equal(store.getState().side, 'parent');

  store.getState().clearSide('parent');
  assert.equal(store.getState().parentSnap, null);
  assert.equal(store.getState().childSnap?.componentId, 'comp_child');

  store.getState().reset();
  assert.equal(store.getState().childSnap, null);
});

test('jointPickSessionStore preserves a snap when relation sync catches up to it', () => {
  const store = useJointPickSessionStore;
  store.getState().reset();

  store.getState().commitSnap(makeFrame('parent'));
  store.getState().setRelation('comp_parent', 'base_link', null, null);
  assert.equal(store.getState().parentSnap?.componentId, 'comp_parent');

  store.getState().setRelation('comp_other', 'base_link', null, null);
  assert.equal(store.getState().parentSnap, null);

  store.getState().reset();
});

test('jointPickSessionStore setMode resets pending picks', () => {
  const store = useJointPickSessionStore;
  store.getState().reset();
  store.getState().setMode('twoPlanes');
  store.getState().pushPending({
    componentId: 'c',
    linkId: 'l',
    linkWorldMatrix: new Array(16).fill(0),
    point: { x: 0, y: 0, z: 0 },
    normal: { x: 0, y: 0, z: 1 },
  });
  assert.equal(store.getState().pending.length, 1);

  store.getState().setMode('twoEdges');
  assert.equal(store.getState().mode, 'twoEdges');
  assert.equal(store.getState().pending.length, 0);

  store.getState().reset();
});
