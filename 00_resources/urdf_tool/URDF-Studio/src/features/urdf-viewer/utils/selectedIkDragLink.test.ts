import assert from 'node:assert/strict';
import test from 'node:test';

import { createAttachedChildLink } from '@/core/robot';
import { DEFAULT_LINK, GeometryType, type InteractionSelection, type UrdfJoint, type UrdfLink } from '@/types';
import { resolveSelectedIkDragLinkId } from './selectedIkDragLink';

const links: Record<string, UrdfLink> = {
  base_link: createAttachedChildLink({
    id: 'base_link',
    name: 'base_link',
  }),
  link_2: createAttachedChildLink({
    id: 'link_2',
    name: 'link_2',
  }),
};

const joints: Record<string, UrdfJoint> = {
  joint_1: {
    id: 'joint_1',
    name: 'joint_1',
    type: 'revolute',
    parentLinkId: 'base_link',
    childLinkId: 'link_2',
    axis: { x: 0, y: 0, z: 1 },
    origin: {
      xyz: { x: 0, y: 0, z: 0.5 },
      rpy: { r: 0, p: 0, y: 0 },
    },
    limit: {
      lower: -1.57,
      upper: 1.57,
      effort: 100,
      velocity: 10,
    },
  } as UrdfJoint,
};

const meshOnlyLinks: Record<string, UrdfLink> = {
  base_link: links.base_link,
  mesh_link: {
    ...DEFAULT_LINK,
    id: 'mesh_link',
    name: 'mesh_link',
    visual: {
      ...DEFAULT_LINK.visual,
      type: GeometryType.MESH,
      meshPath: 'package://demo/mesh_link.stl',
      dimensions: { x: 0, y: 0, z: 0 },
    },
    collision: {
      ...DEFAULT_LINK.collision,
      type: GeometryType.NONE,
      dimensions: { x: 0, y: 0, z: 0 },
    },
  },
};

const meshOnlyJoints: Record<string, UrdfJoint> = {
  joint_1: {
    ...joints.joint_1,
    childLinkId: 'mesh_link',
  },
};

test('resolveSelectedIkDragLinkId keeps explicit ik-handle selections', () => {
  const selection = {
    type: 'link',
    id: 'link_2',
    helperKind: 'ik-handle',
  } as InteractionSelection;

  assert.equal(
    resolveSelectedIkDragLinkId({
      selection,
      ikDragActive: false,
    }),
    'link_2',
  );
});

test('resolveSelectedIkDragLinkId promotes a directly manipulable link while IK drag is active', () => {
  const selection = {
    type: 'link',
    id: 'link_2',
  } as InteractionSelection;

  assert.equal(
    resolveSelectedIkDragLinkId({
      selection,
      ikDragActive: true,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    'link_2',
  );
});

test('resolveSelectedIkDragLinkId promotes mesh-only links while IK drag is active', () => {
  const selection = {
    type: 'link',
    id: 'mesh_link',
  } as InteractionSelection;

  assert.equal(
    resolveSelectedIkDragLinkId({
      selection,
      ikDragActive: true,
      robotLinks: meshOnlyLinks,
      robotJoints: meshOnlyJoints,
      rootLinkId: 'base_link',
    }),
    'mesh_link',
  );
});

test('resolveSelectedIkDragLinkId rejects the root link even when IK drag is active', () => {
  const selection = {
    type: 'link',
    id: 'base_link',
  } as InteractionSelection;

  assert.equal(
    resolveSelectedIkDragLinkId({
      selection,
      ikDragActive: true,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    null,
  );
});

test('resolveSelectedIkDragLinkId ignores plain link selections when IK drag is inactive', () => {
  const selection = {
    type: 'link',
    id: 'link_2',
  } as InteractionSelection;

  assert.equal(
    resolveSelectedIkDragLinkId({
      selection,
      ikDragActive: false,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    null,
  );
});
