import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_JOINT, DEFAULT_LINK, GeometryType, JointType } from '@/types';

import {
  getMjcfJointDisplayName,
  getMjcfLinkDisplayName,
  getMjcfRawDisplayName,
} from './mjcfDisplayNames';

test('getMjcfLinkDisplayName converts anonymous MJCF wrapper bodies into mesh-based labels', () => {
  const link = {
    ...DEFAULT_LINK,
    id: 'world_body_0',
    name: 'world_body_0',
    visual: {
      ...DEFAULT_LINK.visual,
      type: GeometryType.MESH,
      mjcfMesh: {
        name: 'bin',
      },
    },
  };

  assert.equal(getMjcfLinkDisplayName(link), 'Bin');
});

test('getMjcfLinkDisplayName falls back to a numbered body label when no mesh hint exists', () => {
  const link = {
    ...DEFAULT_LINK,
    id: 'world_body_2',
    name: 'world_body_2',
  };

  assert.equal(getMjcfLinkDisplayName(link), 'Body 3');
});

test('getMjcfJointDisplayName rewrites implicit fixed-joint ids using friendly link labels', () => {
  const joint = {
    ...DEFAULT_JOINT,
    id: 'world_to_world_body_1',
    name: 'world_to_world_body_1',
    type: JointType.FIXED,
    parentLinkId: 'world',
    childLinkId: 'world_body_1',
  };

  assert.equal(getMjcfJointDisplayName(joint, 'world', 'Busbin 2'), 'World to Busbin 2');
});

test('getMjcfJointDisplayName preserves authored joint names', () => {
  const joint = {
    ...DEFAULT_JOINT,
    id: 'hinge_root',
    name: 'hinge_root',
    type: JointType.REVOLUTE,
    parentLinkId: 'world',
    childLinkId: 'world_body_1',
  };

  assert.equal(getMjcfJointDisplayName(joint, 'world', 'Busbin 2'), 'hinge_root');
});

test('getMjcfRawDisplayName rewrites generated site names into readable labels', () => {
  assert.equal(getMjcfRawDisplayName('world_body_0_site_1', 'Bin'), 'Bin Site 2');
});

test('getMjcfRawDisplayName keeps supporting legacy double-colon generated site names', () => {
  assert.equal(getMjcfRawDisplayName('world_body_0::site_1', 'Bin'), 'Bin Site 2');
});

test('getMjcfRawDisplayName preserves raw underscore names without generated-body context', () => {
  assert.equal(getMjcfRawDisplayName('bin_site_1'), 'bin_site_1');
});
