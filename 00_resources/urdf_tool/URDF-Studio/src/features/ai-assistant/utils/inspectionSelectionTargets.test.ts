import test from 'node:test';
import assert from 'node:assert/strict';

import type { InspectionReport } from '../../../types/inspection.ts';
import type { RobotState } from '../../../types/robot.ts';
import {
  resolveInspectionIssueRelatedEntities,
  resolveInspectionIssueSelectionTarget,
} from './inspectionSelectionTargets.ts';

function createRobotFixture(): RobotState {
  return {
    name: 'inspection-selection-fixture',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        id: 'base_link',
        name: 'Base Link',
        visual: {
          type: 'box' as RobotState['links'][string]['visual']['type'],
          dimensions: { x: 0.3, y: 0.2, z: 0.1 },
          color: '#cccccc',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: 'box' as RobotState['links'][string]['collision']['type'],
          dimensions: { x: 0.3, y: 0.2, z: 0.1 },
          color: '#cccccc',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
      },
      arm_link: {
        id: 'arm_link',
        name: 'Arm Link',
        visual: {
          type: 'box' as RobotState['links'][string]['visual']['type'],
          dimensions: { x: 0.2, y: 0.1, z: 0.1 },
          color: '#999999',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: 'box' as RobotState['links'][string]['collision']['type'],
          dimensions: { x: 0.2, y: 0.1, z: 0.1 },
          color: '#999999',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
      },
    },
    joints: {
      shoulder_joint: {
        id: 'shoulder_joint',
        name: 'Shoulder Joint',
        type: 'revolute' as RobotState['joints'][string]['type'],
        parentLinkId: 'base_link',
        childLinkId: 'arm_link',
        origin: { xyz: { x: 0, y: 0.1, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        axis: { x: 0, y: 1, z: 0 },
        limit: { lower: -1, upper: 1, effort: 10, velocity: 5 },
        dynamics: { damping: 0.1, friction: 0.1 },
        hardware: { armature: 0.01, motorType: 'servo', motorId: 'M1', motorDirection: 1 },
      },
    },
    selection: { type: null, id: null },
  };
}

function createIssueFixture(): InspectionReport['issues'][number] {
  return {
    type: 'warning',
    title: 'Joint alignment issue',
    description: 'The shoulder joint and arm link are not aligned with the base frame.',
    profileId: 'morph.manipulator',
    itemId: 'joint_axis_consistency',
    relatedIds: ['shoulder_joint', 'arm_link', 'shoulder_joint', 'unknown_id', ''],
  };
}

test('resolveInspectionIssueRelatedEntities keeps valid multi-target entries clickable and deduplicated', () => {
  const relatedEntities = resolveInspectionIssueRelatedEntities(
    createRobotFixture(),
    createIssueFixture(),
  );

  assert.deepEqual(relatedEntities, [
    {
      id: 'shoulder_joint',
      name: 'Shoulder Joint',
      target: { type: 'joint', id: 'shoulder_joint' },
    },
    {
      id: 'arm_link',
      name: 'Arm Link',
      target: { type: 'link', id: 'arm_link' },
    },
    {
      id: 'unknown_id',
      name: 'unknown_id',
      target: null,
    },
  ]);
});

test('resolveInspectionIssueSelectionTarget returns the first valid related entity for fallback single-target actions', () => {
  const target = resolveInspectionIssueSelectionTarget(createRobotFixture(), createIssueFixture());

  assert.deepEqual(target, { type: 'joint', id: 'shoulder_joint' });
});
