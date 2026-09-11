import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, JointType, type InspectionReport, type RobotState } from '@/types';
import { buildConversationContext } from './buildConversationContext.ts';

const createRobotFixture = (): RobotState => ({
  name: 'chat-fixture',
  rootLinkId: 'base_link',
  links: {
    base_link: {
      id: 'base_link',
      name: 'base_link',
      visual: {
        type: GeometryType.BOX,
        dimensions: { x: 0.4, y: 0.2, z: 0.1 },
        color: '#9ca3af',
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      },
      collision: {
        type: GeometryType.BOX,
        dimensions: { x: 0.4, y: 0.2, z: 0.1 },
        color: '#9ca3af',
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      },
      inertial: {
        mass: 2.5,
        inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
      },
    },
  },
  joints: {
    hip_joint: {
      id: 'hip_joint',
      name: 'hip_joint',
      type: JointType.REVOLUTE,
      parentLinkId: 'world',
      childLinkId: 'base_link',
      origin: { xyz: { x: 0, y: 0.1, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      axis: { x: 0, y: 1, z: 0 },
      limit: { lower: -1, upper: 1, effort: 20, velocity: 10 },
      dynamics: { damping: 0.1, friction: 0.1 },
      hardware: { armature: 0.03, motorType: 'servo', motorId: 'M1', motorDirection: 1 },
    },
  },
  inspectionContext: {
    sourceFormat: 'mjcf',
    mjcf: {
      siteCount: 2,
      tendonCount: 1,
      tendonActuatorCount: 1,
      bodiesWithSites: [{ bodyId: 'base_link', siteCount: 2, siteNames: ['a_site', 'b_site'] }],
      tendons: [
        {
          name: 'main_tendon',
          type: 'spatial',
          attachmentRefs: ['a_site', 'b_site'],
          attachments: [],
          actuatorNames: ['M1'],
        },
      ],
    },
  },
  selection: { type: 'link', id: 'base_link' },
});

const reportFixture: InspectionReport = {
  summary: 'Found one warning on joint limit configuration.',
  overallScore: 82,
  maxScore: 100,
  profileScores: {
    'workflow.hardware_config': 7.5,
  },
  issues: [
    {
      type: 'warning',
      title: 'Joint range may be too narrow',
      description: 'The hip joint range can limit reachable workspace.',
      profileId: 'workflow.hardware_config',
      itemId: 'effort_velocity_limits',
      evidenceLevel: 'L1',
      score: 6,
      relatedIds: ['hip_joint', 'base_link'],
    },
  ],
};

test('buildConversationContext includes robot snapshot in general mode without inspection report payload', () => {
  const contextString = buildConversationContext({
    mode: 'general',
    robot: createRobotFixture(),
  });

  const payload = JSON.parse(contextString) as Record<string, unknown>;
  assert.equal(payload.mode, 'general');
  assert.ok(payload.robot);
  assert.equal(payload.inspectionReport, undefined);
});

test('buildConversationContext includes compact report snapshot for inspection-followup mode', () => {
  const contextString = buildConversationContext({
    mode: 'inspection-followup',
    robot: createRobotFixture(),
    inspectionReport: reportFixture,
    selectedEntity: {
      type: 'joint',
      componentId: 'arm',
      entityId: 'hip_joint',
    },
    focusedIssue: {
      type: 'warning',
      title: 'Joint range may be too narrow',
      description: 'The hip joint range can limit reachable workspace.',
      profileId: 'workflow.hardware_config',
      itemId: 'effort_velocity_limits',
      evidenceLevel: 'L1',
      score: 6,
      relatedIds: ['hip_joint', 'base_link'],
    },
  });

  const payload = JSON.parse(contextString) as {
    mode: string;
    robot: { name: string; jointCount: number };
    inspectionReport: {
      summary: string;
      profileScores?: Record<string, number>;
      issues: Array<{
        profileId?: string;
        itemId?: string;
        evidenceLevel?: string;
        relatedIds?: string[];
      }>;
    };
    selectedEntity: { type: string; componentId: string; entityId: string; name: string };
    focusedIssue: { title: string; profileId?: string; evidenceLevel?: string; relatedIds?: string[] };
  };

  assert.equal(payload.mode, 'inspection-followup');
  assert.equal(payload.robot.name, 'chat-fixture');
  assert.equal(payload.robot.jointCount, 1);
  assert.equal(payload.inspectionReport.summary, reportFixture.summary);
  assert.deepEqual(payload.inspectionReport.profileScores, {
    'workflow.hardware_config': 7.5,
  });
  assert.deepEqual(payload.inspectionReport.issues[0]?.relatedIds, ['base_link', 'hip_joint']);
  assert.equal(payload.inspectionReport.issues[0]?.profileId, 'workflow.hardware_config');
  assert.equal(payload.inspectionReport.issues[0]?.itemId, 'effort_velocity_limits');
  assert.equal(payload.inspectionReport.issues[0]?.evidenceLevel, 'L1');
  assert.deepEqual(payload.selectedEntity, {
    type: 'joint',
    componentId: 'arm',
    entityId: 'hip_joint',
    name: 'hip_joint',
  });
  assert.equal(payload.focusedIssue.title, 'Joint range may be too narrow');
  assert.equal(payload.focusedIssue.profileId, 'workflow.hardware_config');
  assert.equal(payload.focusedIssue.evidenceLevel, 'L1');
  assert.deepEqual(payload.focusedIssue.relatedIds, ['base_link', 'hip_joint']);
});
