import test from 'node:test';
import assert from 'node:assert/strict';

import { reconcileUsdCollisionMeshAssignments } from './usdCollisionMeshAssignments.ts';

test('assigns unique collision object indices on first load', () => {
  const assignments = reconcileUsdCollisionMeshAssignments({
    meshes: [
      { meshId: 'collision-box', authoredOrder: 0 },
      { meshId: 'collision-sphere', authoredOrder: 1 },
    ],
    currentCount: 2,
  });

  assert.equal(assignments.get('collision-box'), 0);
  assert.equal(assignments.get('collision-sphere'), 1);
});

test('drops the deleted collision mesh and shifts later meshes down', () => {
  const assignments = reconcileUsdCollisionMeshAssignments({
    meshes: [
      { meshId: 'collision-a', authoredOrder: 0 },
      { meshId: 'collision-b', authoredOrder: 1 },
      { meshId: 'collision-c', authoredOrder: 2 },
    ],
    currentCount: 2,
    previousAssignments: new Map([
      ['collision-a', 0],
      ['collision-b', 1],
      ['collision-c', 2],
    ]),
    deletedObjectIndex: 1,
  });

  assert.equal(assignments.get('collision-a'), 0);
  assert.equal(assignments.get('collision-b'), undefined);
  assert.equal(assignments.get('collision-c'), 1);
});

test('handles deleting the first collision mesh without reusing its slot', () => {
  const assignments = reconcileUsdCollisionMeshAssignments({
    meshes: [
      { meshId: 'collision-primary', authoredOrder: 0 },
      { meshId: 'collision-secondary', authoredOrder: 1 },
    ],
    currentCount: 1,
    previousAssignments: new Map([
      ['collision-primary', 0],
      ['collision-secondary', 1],
    ]),
    deletedObjectIndex: 0,
  });

  assert.equal(assignments.get('collision-primary'), undefined);
  assert.equal(assignments.get('collision-secondary'), 0);
});
