import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_JOINT, DEFAULT_LINK, JointType, type RobotState, type UrdfJoint } from '@/types';
import { generateRobotBomCsv, type BomLabels } from './bom';

const jointWithMotor: UrdfJoint = {
  ...DEFAULT_JOINT,
  id: 'joint-1',
  name: 'joint-1',
  type: JointType.REVOLUTE,
  parentLinkId: 'base',
  childLinkId: 'child',
  origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
  limit: { lower: 0, upper: 1, effort: 1, velocity: 1 },
  hardware: {
    armature: 1,
    brand: 'Test',
    motorId: 'M1',
    motorType: 'servo',
    motorDirection: 1,
  },
};

const jointWithoutMotor: UrdfJoint = {
  ...jointWithMotor,
  id: 'joint-2',
  name: 'joint-2',
  hardware: {
    ...jointWithMotor.hardware,
    motorType: 'None',
  },
};

const robot: RobotState = {
  name: 'bom-test',
  links: {
    base: {
      ...DEFAULT_LINK,
      id: 'base',
      name: 'base',
    },
    child: {
      ...DEFAULT_LINK,
      id: 'child',
      name: 'child',
    },
  },
  joints: {
    'joint-1': jointWithMotor,
    'joint-2': jointWithoutMotor,
  },
  rootLinkId: 'base',
  selection: { type: null, id: null },
};

const labels: BomLabels = {
  armature: 'Armature',
  direction: 'Direction',
  jointName: 'Joint',
  lower: 'Lower',
  motorId: 'Motor ID',
  motorType: 'Motor Type',
  type: 'Type',
  upper: 'Upper',
};

test('generateRobotBomCsv emits headers and only joints with motors', () => {
  const csv = generateRobotBomCsv(robot, labels);
  const lines = csv.split('\n');

  assert.strictEqual(lines[0], 'Joint,Type,Motor Type,Motor ID,Direction,Armature,Lower,Upper');
  assert.strictEqual(lines.length, 2);

  const entry = lines[1].split(',');
  assert.deepStrictEqual(entry, ['joint-1', JointType.REVOLUTE, 'servo', 'M1', '1', '1', '0', '1']);
});
