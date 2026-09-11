import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveActiveViewerJointKeyFromSelection } from './activeJointSelection.ts';

test('resolveActiveViewerJointKeyFromSelection resolves a controllable joint selection by key', () => {
  const joints = {
    hip_joint: {
      name: 'hip_joint',
      jointType: 'revolute',
      child: { name: 'upper_leg' },
    },
  };

  assert.equal(
    resolveActiveViewerJointKeyFromSelection(joints, { type: 'joint', id: 'hip_joint' }),
    'hip_joint',
  );
});

test('resolveActiveViewerJointKeyFromSelection resolves the parent joint for a selected child link', () => {
  const joints = {
    knee_joint: {
      name: 'knee_joint',
      jointType: 'continuous',
      child: { name: 'lower_leg' },
    },
  };

  assert.equal(
    resolveActiveViewerJointKeyFromSelection(joints, { type: 'link', id: 'lower_leg' }),
    'knee_joint',
  );
});

test('resolveActiveViewerJointKeyFromSelection resolves the parent joint for structured joints using childLinkId', () => {
  const joints = {
    ankle_joint: {
      id: 'ankle_joint',
      name: 'ankle_joint',
      type: 'revolute',
      childLinkId: 'foot_link',
    },
  };

  assert.equal(
    resolveActiveViewerJointKeyFromSelection(joints, { type: 'link', id: 'foot_link' }),
    'ankle_joint',
  );
});

test('resolveActiveViewerJointKeyFromSelection climbs past fixed parents to the nearest controllable joint', () => {
  const joints = {
    hip_joint: {
      id: 'hip_joint',
      name: 'hip_joint',
      type: 'revolute',
      parentLinkId: 'base_link',
      childLinkId: 'upper_leg',
    },
    shin_adapter_fixed: {
      id: 'shin_adapter_fixed',
      name: 'shin_adapter_fixed',
      type: 'fixed',
      parentLinkId: 'upper_leg',
      childLinkId: 'lower_leg',
    },
  };

  assert.equal(
    resolveActiveViewerJointKeyFromSelection(joints, { type: 'link', id: 'lower_leg' }),
    'hip_joint',
  );
});

test('resolveActiveViewerJointKeyFromSelection climbs structured runtime joints using parent and child names', () => {
  const joints = {
    drive_joint: {
      id: 'drive_joint',
      name: 'drive_joint',
      jointType: 'revolute',
      parent: { name: 'base_link' },
      child: { name: 'carrier_link' },
    },
    helper_fixed: {
      id: 'helper_fixed',
      name: 'helper_fixed',
      jointType: 'fixed',
      parent: { name: 'carrier_link' },
      child: { name: 'tool_link' },
    },
  };

  assert.equal(
    resolveActiveViewerJointKeyFromSelection(joints, { type: 'link', id: 'tool_link' }),
    'drive_joint',
  );
});

test('resolveActiveViewerJointKeyFromSelection ignores non-controllable joints', () => {
  const joints = {
    base_fixed_joint: {
      name: 'base_fixed_joint',
      jointType: 'fixed',
      child: { name: 'base_link' },
    },
  };

  assert.equal(
    resolveActiveViewerJointKeyFromSelection(joints, { type: 'joint', id: 'base_fixed_joint' }),
    null,
  );
});
