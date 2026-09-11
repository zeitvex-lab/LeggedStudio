import assert from 'node:assert/strict';
import test from 'node:test';

import { GeometryType, type UrdfLink } from '@/types';

import { applyLinkPatch } from './linkPatch.ts';

function createLink(): UrdfLink {
  return {
    id: 'Trunk',
    name: 'Trunk',
    visual: {
      type: GeometryType.BOX,
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#ffffff',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
    collision: {
      type: GeometryType.BOX,
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#ffffff',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
    inertial: {
      mass: 12.34,
      origin: {
        xyz: { x: 0.055136, y: -0.000001, z: 0.105062 },
        rpy: { r: 0, p: -0.018, y: 0 },
      },
      inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 2, iyz: 0, izz: 3 },
    },
  };
}

test('applyLinkPatch preserves inertial mass when updating only COM position', () => {
  const nextLink = applyLinkPatch(createLink(), {
    inertial: {
      origin: {
        xyz: { x: 0.123456 },
      },
    } as UrdfLink['inertial'],
  });

  assert.equal(nextLink.inertial?.mass, 12.34);
  assert.equal(nextLink.inertial?.origin?.xyz.x, 0.123456);
  assert.equal(nextLink.inertial?.origin?.xyz.y, -0.000001);
  assert.equal(nextLink.inertial?.origin?.rpy.p, -0.018);
});

test('applyLinkPatch preserves inertial origin when updating only tensor fields', () => {
  const nextLink = applyLinkPatch(createLink(), {
    inertial: {
      inertia: { ixx: 4 },
    } as UrdfLink['inertial'],
  });

  assert.equal(nextLink.inertial?.mass, 12.34);
  assert.equal(nextLink.inertial?.origin?.xyz.x, 0.055136);
  assert.equal(nextLink.inertial?.inertia.ixx, 4);
  assert.equal(nextLink.inertial?.inertia.iyy, 2);
});
