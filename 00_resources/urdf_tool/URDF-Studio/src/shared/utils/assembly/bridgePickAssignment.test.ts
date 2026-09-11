import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveBridgePickAssignment } from './bridgePickAssignment.ts';

test('resolveBridgePickAssignment fills parent first and child second', () => {
  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: 'component_a',
      parentComponentId: '',
      childComponentId: '',
      preferredTarget: 'child',
    }),
    'parent',
  );

  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: 'component_b',
      parentComponentId: 'component_a',
      childComponentId: '',
      preferredTarget: 'parent',
    }),
    'child',
  );
});

test('resolveBridgePickAssignment updates the side that already owns the component', () => {
  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: 'component_a',
      parentComponentId: 'component_a',
      childComponentId: 'component_b',
      preferredTarget: 'child',
    }),
    'parent',
  );

  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: 'component_b',
      parentComponentId: 'component_a',
      childComponentId: 'component_b',
      preferredTarget: 'parent',
    }),
    'child',
  );
});

test('resolveBridgePickAssignment does not assign a picked component to the opposite occupied side', () => {
  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: 'component_a',
      parentComponentId: 'component_a',
      childComponentId: '',
      preferredTarget: 'child',
    }),
    'parent',
  );

  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: 'component_a',
      parentComponentId: '',
      childComponentId: 'component_a',
      preferredTarget: 'parent',
    }),
    'child',
  );
});

test('resolveBridgePickAssignment ignores empty component picks', () => {
  assert.equal(
    resolveBridgePickAssignment({
      selectedComponentId: '',
      parentComponentId: 'component_a',
      childComponentId: 'component_b',
      preferredTarget: 'parent',
    }),
    null,
  );
});
