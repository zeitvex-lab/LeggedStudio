import assert from 'node:assert/strict';
import test from 'node:test';

import { createJointPanelStore } from './jointPanelStore';

test('joint panel store patches angles and active joint independently', () => {
  const store = createJointPanelStore({
    jointAngles: { shoulder_joint: 0 },
    activeJoint: null,
  });

  let notifications = 0;
  const unsubscribe = store.subscribe(() => {
    notifications += 1;
  });

  assert.equal(store.patchJointAngles({ shoulder_joint: 0 }), false);
  assert.equal(store.patchJointAngles({ shoulder_joint: 0.5 }), true);
  assert.equal(store.setActiveJoint('shoulder_joint'), true);
  assert.equal(store.setActiveJoint('shoulder_joint'), false);

  const snapshot = store.getSnapshot();
  assert.deepEqual(snapshot.jointAngles, { shoulder_joint: 0.5 });
  assert.equal(snapshot.activeJoint, 'shoulder_joint');
  assert.equal(snapshot.activeJointAutoScroll, true);
  assert.equal(notifications, 2);

  unsubscribe();
});

test('joint panel store reset replaces previous snapshot', () => {
  const store = createJointPanelStore({
    jointAngles: { elbow_joint: 1.2 },
    activeJoint: 'elbow_joint',
  });

  assert.equal(
    store.reset({
      jointAngles: { wrist_joint: -0.3 },
      activeJoint: null,
    }),
    true,
  );

  const snapshot = store.getSnapshot();
  assert.deepEqual(snapshot.jointAngles, { wrist_joint: -0.3 });
  assert.equal(snapshot.activeJoint, null);
  assert.equal(snapshot.activeJointAutoScroll, false);
});

test('joint panel store preserves explicit auto-scroll suppression for same active joint', () => {
  const store = createJointPanelStore();

  assert.equal(store.setActiveJoint('shoulder_joint', { autoScroll: false }), true);
  assert.equal(store.setActiveJoint('shoulder_joint'), false);

  let snapshot = store.getSnapshot();
  assert.equal(snapshot.activeJoint, 'shoulder_joint');
  assert.equal(snapshot.activeJointAutoScroll, false);

  assert.equal(store.setActiveJoint('elbow_joint'), true);

  snapshot = store.getSnapshot();
  assert.equal(snapshot.activeJoint, 'elbow_joint');
  assert.equal(snapshot.activeJointAutoScroll, true);
});
