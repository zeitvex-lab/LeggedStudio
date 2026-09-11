import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  addMeasureGroup,
  appendMeasurePoint,
  applyMeasurePick,
  clearActiveMeasureGroup,
  clearMeasureState,
  clearMeasureSlot,
  createEmptyMeasureState,
  createMeasureTarget,
  getActiveMeasureGroup,
  getActiveMeasureMeasurement,
  getLinkMeasureCenter,
  getMeasureRelativePose,
  getMeasureStateMeasurements,
  getObjectWorldCenter,
  getMeasurementMetrics,
  removeMeasureGroup,
  setActiveMeasureGroup,
  setMeasureMode,
  undoMeasureState,
} from './measurements.ts';

test('creates a single measurement for the active group and keeps both slots selected', () => {
  const first = createMeasureTarget({
    linkName: 'base_link',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(0, 0, 0),
  });
  const second = createMeasureTarget({
    linkName: 'arm_link',
    objectType: 'collision',
    objectIndex: 1,
    point: new THREE.Vector3(3, 4, 12),
  });

  const afterFirstPick = applyMeasurePick(createEmptyMeasureState(), first);
  const afterFirstGroup = getActiveMeasureGroup(afterFirstPick);
  assert.equal(afterFirstGroup.first?.key, first.key);
  assert.equal(afterFirstGroup.second, null);
  assert.equal(afterFirstGroup.activeSlot, 'second');
  assert.equal(getMeasureStateMeasurements(afterFirstPick).length, 0);

  const completed = applyMeasurePick(afterFirstPick, second);
  const completedGroup = getActiveMeasureGroup(completed);
  const measurement = getActiveMeasureMeasurement(completed);

  assert.ok(measurement);
  assert.equal(measurement.first.key, first.key);
  assert.equal(measurement.second.key, second.key);
  assert.equal(measurement.distance, 13);
  assert.deepEqual(measurement.delta, { x: 3, y: 4, z: 12 });
  assert.equal(completedGroup.first?.key, first.key);
  assert.equal(completedGroup.second?.key, second.key);
  assert.equal(completedGroup.activeSlot, 'second');
});

test('re-picking the active slot overwrites the same group instead of creating extra measurements', () => {
  const first = createMeasureTarget({
    linkName: 'base_link',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(0, 0, 0),
  });
  const secondA = createMeasureTarget({
    linkName: 'arm_link_a',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(1, 0, 0),
  });
  const secondB = createMeasureTarget({
    linkName: 'arm_link_b',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(2, 0, 0),
  });

  const baseState = applyMeasurePick(applyMeasurePick(createEmptyMeasureState(), first), secondA);
  const updatedState = applyMeasurePick(baseState, secondB);
  const activeGroup = getActiveMeasureGroup(updatedState);
  const measurements = getMeasureStateMeasurements(updatedState);

  assert.equal(measurements.length, 1);
  assert.equal(activeGroup.first?.key, first.key);
  assert.equal(activeGroup.second?.key, secondB.key);
  assert.equal(measurements[0].second.key, secondB.key);
});

test('supports multiple measurement groups and keeps one measurement per group', () => {
  const firstGroupState = applyMeasurePick(
    applyMeasurePick(
      createEmptyMeasureState(),
      createMeasureTarget({
        linkName: 'group1_a',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 0, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'group1_b',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(1, 0, 0),
    }),
  );

  const withSecondGroup = addMeasureGroup(firstGroupState);
  const secondGroupState = applyMeasurePick(
    applyMeasurePick(
      withSecondGroup,
      createMeasureTarget({
        linkName: 'group2_a',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 1, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'group2_b',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(0, 3, 0),
    }),
  );

  const measurements = getMeasureStateMeasurements(secondGroupState);
  assert.equal(measurements.length, 2);
  assert.equal(measurements[0].groupIndex, 1);
  assert.equal(measurements[1].groupIndex, 2);

  const firstGroupId = secondGroupState.groups[0].id;
  const switched = setActiveMeasureGroup(secondGroupState, firstGroupId);
  const activeMeasurement = getActiveMeasureMeasurement(switched);
  assert.ok(activeMeasurement);
  assert.equal(activeMeasurement.groupIndex, 1);
});

test('removes a measurement group and activates the nearest remaining group', () => {
  const firstGroupState = applyMeasurePick(
    applyMeasurePick(
      createEmptyMeasureState(),
      createMeasureTarget({
        linkName: 'group1_a',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 0, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'group1_b',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(1, 0, 0),
    }),
  );

  const secondGroup = addMeasureGroup(firstGroupState);
  const secondGroupState = applyMeasurePick(
    applyMeasurePick(
      secondGroup,
      createMeasureTarget({
        linkName: 'group2_a',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 1, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'group2_b',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(0, 2, 0),
    }),
  );

  const removed = removeMeasureGroup(secondGroupState, secondGroupState.groups[1].id);

  assert.equal(removed.groups.length, 1);
  assert.equal(removed.activeGroupId, removed.groups[0].id);
  assert.equal(getMeasureStateMeasurements(removed).length, 1);
  assert.equal(getActiveMeasureMeasurement(removed)?.groupIndex, 1);
});

test('removing the last measurement group resets the measure state', () => {
  const completed = applyMeasurePick(
    applyMeasurePick(
      createEmptyMeasureState(),
      createMeasureTarget({
        linkName: 'base_link',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 0, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'arm_link',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(1, 0, 0),
    }),
  );

  const reset = removeMeasureGroup(completed, completed.groups[0].id);

  assert.equal(reset.groups.length, 1);
  assert.equal(reset.activeGroupId, reset.groups[0].id);
  assert.equal(reset.groups[0].first, null);
  assert.equal(reset.groups[0].second, null);
  assert.equal(getMeasureStateMeasurements(reset).length, 0);
});

test('clears the requested measure slot and keeps the other slot intact', () => {
  const first = createMeasureTarget({
    linkName: 'base_link',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(0, 0, 0),
  });
  const second = createMeasureTarget({
    linkName: 'arm_link',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(1, 2, 3),
  });

  const completed = applyMeasurePick(applyMeasurePick(createEmptyMeasureState(), first), second);
  const cleared = clearMeasureSlot(completed, 'second');
  const activeGroup = getActiveMeasureGroup(cleared);

  assert.equal(activeGroup.first?.key, first.key);
  assert.equal(activeGroup.second, null);
  assert.equal(activeGroup.activeSlot, 'second');
});

test('clears only the active measurement group when requested', () => {
  const completed = applyMeasurePick(
    applyMeasurePick(
      createEmptyMeasureState(),
      createMeasureTarget({
        linkName: 'group_a',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 0, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'group_b',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(2, 0, 0),
    }),
  );

  const cleared = clearActiveMeasureGroup(completed);
  const activeGroup = getActiveMeasureGroup(cleared);

  assert.equal(activeGroup.first, null);
  assert.equal(activeGroup.second, null);
  assert.equal(getMeasureStateMeasurements(cleared).length, 0);
});

test('clearMeasureState recreates a single empty measurement group', () => {
  const completed = applyMeasurePick(
    applyMeasurePick(
      createEmptyMeasureState(),
      createMeasureTarget({
        linkName: 'group_a',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(0, 0, 0),
      }),
    ),
    createMeasureTarget({
      linkName: 'group_b',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(2, 0, 0),
    }),
  );

  const cleared = clearMeasureState();

  assert.equal(cleared.groups.length, 1);
  assert.equal(cleared.activeGroupId, cleared.groups[0].id);
  assert.equal(cleared.groups[0].first, null);
  assert.equal(cleared.groups[0].second, null);
  assert.equal(getMeasureStateMeasurements(cleared).length, 0);
  assert.notEqual(cleared.activeGroupId, completed.activeGroupId);
});

test('computes xyz decomposition for diagonal mesh measurements', () => {
  const metrics = getMeasurementMetrics(new THREE.Vector3(1, 2, 3), new THREE.Vector3(4, 6, 15));

  assert.equal(metrics.distance, 13);
  assert.deepEqual(metrics.delta, { x: 3, y: 4, z: 12 });
  assert.deepEqual(metrics.absoluteDelta, { x: 3, y: 4, z: 12 });
  assert.equal(metrics.isDiagonal, true);
});

test('marks axis-aligned mesh measurements as non-diagonal', () => {
  const metrics = getMeasurementMetrics(new THREE.Vector3(5, 1, -2), new THREE.Vector3(5, 1, 8));

  assert.equal(metrics.distance, 10);
  assert.deepEqual(metrics.delta, { x: 0, y: 0, z: 10 });
  assert.equal(metrics.isDiagonal, false);
});

test('computes a relative pose from the first anchor frame to the second anchor frame', () => {
  const firstPose = new THREE.Matrix4().makeTranslation(1, 0, 0);
  const secondPose = new THREE.Matrix4().makeRotationZ(Math.PI / 2).setPosition(1, 2, 0);

  const relativePose = getMeasureRelativePose(firstPose, secondPose);

  assert.ok(relativePose);
  assert.deepEqual(relativePose.translation, { x: 0, y: 2, z: 0 });
  assert.equal(relativePose.rpy.r, 0);
  assert.equal(relativePose.rpy.p, 0);
  assert.ok(Math.abs(relativePose.rpy.y - Math.PI / 2) < 1e-6);
  assert.equal(relativePose.quaternion.x, 0);
  assert.equal(relativePose.quaternion.y, 0);
  assert.ok(Math.abs(relativePose.quaternion.z - Math.sqrt(0.5)) < 1e-6);
  assert.ok(Math.abs(relativePose.quaternion.w - Math.sqrt(0.5)) < 1e-6);
  assert.deepEqual(relativePose.axisAngle.axis, { x: 0, y: 0, z: 1 });
  assert.ok(Math.abs(relativePose.axisAngle.angle - Math.PI / 2) < 1e-6);
});

test('includes the relative pose on completed measurements when both targets expose pose matrices', () => {
  const firstPose = new THREE.Matrix4().makeTranslation(1, 2, 3);
  const secondPose = new THREE.Matrix4().makeRotationZ(Math.PI / 2).setPosition(4, 6, 3);

  const completed = applyMeasurePick(
    applyMeasurePick(
      createEmptyMeasureState(),
      createMeasureTarget({
        linkName: 'base_link',
        objectType: 'visual',
        objectIndex: 0,
        point: new THREE.Vector3(1, 2, 3),
        poseWorldMatrix: firstPose,
      }),
    ),
    createMeasureTarget({
      linkName: 'tool_link',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(4, 6, 3),
      poseWorldMatrix: secondPose,
    }),
  );

  const measurement = getActiveMeasureMeasurement(completed);

  assert.ok(measurement?.relativePose);
  assert.deepEqual(measurement.relativePose.translation, { x: 3, y: 4, z: 0 });
  assert.ok(Math.abs(measurement.relativePose.rpy.y - Math.PI / 2) < 1e-6);
});

test('computes world center from the selected mesh object instead of the hit surface point', () => {
  const group = new THREE.Group();
  group.position.set(10, -3, 2);

  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 4, 6), new THREE.MeshBasicMaterial());
  mesh.position.set(1, 2, 3);
  group.add(mesh);
  group.updateMatrixWorld(true);

  const center = getObjectWorldCenter(group);

  assert.deepEqual(center.toArray(), [11, -1, 5]);
});

test('uses the selected visual body center instead of the full link subtree center', () => {
  const link = new THREE.Group() as THREE.Group & { isURDFLink?: boolean };
  link.name = 'base_link';
  link.isURDFLink = true;

  const visual = new THREE.Group() as THREE.Group & { isURDFVisual?: boolean };
  visual.isURDFVisual = true;
  const visualMesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial());
  visualMesh.position.set(1, 0, 0);
  visual.add(visualMesh);
  link.add(visual);

  const joint = new THREE.Group() as THREE.Group & { isURDFJoint?: boolean };
  joint.isURDFJoint = true;
  const childLink = new THREE.Group() as THREE.Group & { isURDFLink?: boolean };
  childLink.name = 'child_link';
  childLink.isURDFLink = true;
  const childVisual = new THREE.Group() as THREE.Group & { isURDFVisual?: boolean };
  childVisual.isURDFVisual = true;
  const childMesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial());
  childMesh.position.set(100, 0, 0);
  childVisual.add(childMesh);
  childLink.add(childVisual);
  joint.add(childLink);
  link.add(joint);

  link.updateMatrixWorld(true);

  const center = getLinkMeasureCenter(link, 'visual', 0);

  assert.deepEqual(center.toArray(), [1, 0, 0]);
});

test('uses the selected direct visual body center when a link has multiple visual bodies', () => {
  const link = new THREE.Group() as THREE.Group & { isURDFLink?: boolean };
  link.name = 'arm_link';
  link.isURDFLink = true;

  const firstVisual = new THREE.Group() as THREE.Group & { isURDFVisual?: boolean };
  firstVisual.isURDFVisual = true;
  const firstMesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial());
  firstMesh.position.set(2, 0, 0);
  firstVisual.add(firstMesh);

  const secondVisual = new THREE.Group() as THREE.Group & { isURDFVisual?: boolean };
  secondVisual.isURDFVisual = true;
  const secondMesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial());
  secondMesh.position.set(8, 0, 0);
  secondVisual.add(secondMesh);

  link.add(firstVisual);
  link.add(secondVisual);
  link.updateMatrixWorld(true);

  const center = getLinkMeasureCenter(link, 'visual', 1);

  assert.deepEqual(center.toArray(), [8, 0, 0]);
});

test('defaults to object mode and resets state when switching modes', () => {
  const empty = createEmptyMeasureState();
  assert.equal(empty.mode, 'object');

  const withPick = applyMeasurePick(
    empty,
    createMeasureTarget({
      linkName: 'base_link',
      objectType: 'visual',
      objectIndex: 0,
      point: new THREE.Vector3(0, 0, 0),
    }),
  );

  const pointState = setMeasureMode(withPick, 'point');
  assert.equal(pointState.mode, 'point');
  assert.equal(pointState.groups.length, 1);
  assert.equal(pointState.groups[0].first, null);
  assert.equal(pointState.groups[0].second, null);

  // Switching to the same mode is a no-op (preserves the existing state reference).
  assert.equal(setMeasureMode(pointState, 'point'), pointState);

  const backToObject = setMeasureMode(pointState, 'object');
  assert.equal(backToObject.mode, 'object');
});

test('appendMeasurePoint fills both slots with unique, pose-less point targets', () => {
  const afterFirst = appendMeasurePoint(
    createEmptyMeasureState('point'),
    new THREE.Vector3(0, 0, 0),
  );
  const firstGroup = getActiveMeasureGroup(afterFirst);
  assert.ok(firstGroup.first);
  assert.equal(firstGroup.second, null);
  assert.equal(firstGroup.activeSlot, 'second');
  assert.equal(firstGroup.first?.poseWorldMatrix, null);
  assert.equal(getMeasureStateMeasurements(afterFirst).length, 0);

  const completed = appendMeasurePoint(afterFirst, new THREE.Vector3(3, 4, 12));
  const measurement = getActiveMeasureMeasurement(completed);
  assert.ok(measurement);
  assert.equal(measurement.distance, 13);
  assert.deepEqual(measurement.delta, { x: 3, y: 4, z: 12 });
  // Free points carry no orientation, so no relative pose is derived.
  assert.equal(measurement.relativePose, null);
  // Each point gets a distinct key so endpoints never collapse together.
  assert.notEqual(measurement.first.key, measurement.second.key);
});

test('appendMeasurePoint starts a new group once the active pair is complete', () => {
  const completed = appendMeasurePoint(
    appendMeasurePoint(createEmptyMeasureState('point'), new THREE.Vector3(0, 0, 0)),
    new THREE.Vector3(1, 0, 0),
  );
  assert.equal(completed.groups.length, 1);

  const afterThirdClick = appendMeasurePoint(completed, new THREE.Vector3(5, 0, 0));
  assert.equal(afterThirdClick.groups.length, 2);
  const activeGroup = getActiveMeasureGroup(afterThirdClick);
  assert.ok(activeGroup.first);
  assert.equal(activeGroup.second, null);
  assert.equal(getMeasureStateMeasurements(afterThirdClick).length, 1);
});

test('undoMeasureState clears the in-progress point before removing completed groups', () => {
  const inProgress = appendMeasurePoint(createEmptyMeasureState('point'), new THREE.Vector3(0, 0, 0));
  const afterUndo = undoMeasureState(inProgress);
  const undoneGroup = getActiveMeasureGroup(afterUndo);
  assert.equal(undoneGroup.first, null);
  assert.equal(undoneGroup.second, null);
  assert.equal(afterUndo.mode, 'point');
});

test('clearMeasureState, addMeasureGroup and removeMeasureGroup preserve the active mode', () => {
  const pointState = appendMeasurePoint(
    createEmptyMeasureState('point'),
    new THREE.Vector3(0, 0, 0),
  );

  assert.equal(clearMeasureState('point').mode, 'point');
  assert.equal(addMeasureGroup(pointState).mode, 'point');

  // Removing the only group recreates an empty state but keeps the mode.
  const onlyGroupId = pointState.groups[0].id;
  const afterRemove = removeMeasureGroup(pointState, onlyGroupId);
  assert.equal(afterRemove.groups.length, 1);
  assert.equal(afterRemove.mode, 'point');
});

test('createMeasureTarget honours key/label overrides and falls back to link defaults', () => {
  const overridden = createMeasureTarget({
    linkName: '',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(1, 2, 3),
    key: 'point:custom',
    label: 'P1',
  });
  assert.equal(overridden.key, 'point:custom');
  assert.equal(overridden.label, 'P1');

  const defaulted = createMeasureTarget({
    linkName: 'base_link',
    objectType: 'visual',
    objectIndex: 0,
    point: new THREE.Vector3(0, 0, 0),
  });
  assert.equal(defaulted.key, 'link:base_link');
  assert.equal(defaulted.label, 'base_link');
});
