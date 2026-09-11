import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_LINK, GeometryType, type RobotData, type UrdfVisual } from '@/types';

import {
  cloneCollisionGeometry,
  collectCollisionTargets,
  createCollisionTargetId,
  filterCollisionTargets,
  getCollisionTargetLinkGroupKey,
  normalizeCollisionGeometry,
} from './collisionTargets.ts';

function createCollisionGeometry(
  id: string,
  type: GeometryType,
  overrides: Partial<UrdfVisual> = {},
): UrdfVisual {
  return {
    name: id,
    type,
    dimensions: { x: 1, y: 2, z: 3 },
    color: '#ef4444',
    origin: {
      xyz: { x: 0.1, y: 0.2, z: 0.3 },
      rpy: { r: 0.4, p: 0.5, y: 0.6 },
    },
    ...overrides,
  };
}

function createTargetRobot(): RobotData {
  return {
    name: 'target-test',
    rootLinkId: 'base',
    links: {
      base: {
        ...DEFAULT_LINK,
        id: 'base',
        name: 'Base Link',
        collision: createCollisionGeometry('primary-box', GeometryType.BOX),
        collisionBodies: [createCollisionGeometry('secondary-mesh', GeometryType.MESH)],
      },
      wrist: {
        ...DEFAULT_LINK,
        id: 'wrist',
        name: 'Wrist Link',
        collision: createCollisionGeometry('wrist-cylinder', GeometryType.CYLINDER),
      },
    },
    joints: {},
  };
}

test('collectCollisionTargets assigns stable ids, component metadata, body indexes, and cloned geometry', () => {
  const robot = createTargetRobot();
  const source = {
    kind: 'assembly' as const,
    assembly: {
      name: 'target assembly',
      transform: {
        position: { x: 0, y: 0, z: 0 },
        rotation: { r: 0, p: 0, y: 0 },
      },
      components: {
        arm: {
          id: 'arm',
          name: 'Arm Component',
          robot,
          sourceFile: 'arm.urdf',
          transform: {
            position: { x: 0, y: 0, z: 0 },
            rotation: { r: 0, p: 0, y: 0 },
          },
          visible: true,
        },
      },
      bridges: {},
    },
  };

  const targets = collectCollisionTargets(source);

  assert.deepEqual(
    targets.map((target) => ({
      id: target.id,
      componentId: target.componentId,
      componentName: target.componentName,
      linkId: target.linkId,
      linkName: target.linkName,
      objectIndex: target.objectIndex,
      bodyIndex: target.bodyIndex,
      isPrimary: target.isPrimary,
      sequenceIndex: target.sequenceIndex,
    })),
    [
      {
        id: 'arm::base::0',
        componentId: 'arm',
        componentName: 'Arm Component',
        linkId: 'base',
        linkName: 'Base Link',
        objectIndex: 0,
        bodyIndex: null,
        isPrimary: true,
        sequenceIndex: 0,
      },
      {
        id: 'arm::base::1',
        componentId: 'arm',
        componentName: 'Arm Component',
        linkId: 'base',
        linkName: 'Base Link',
        objectIndex: 1,
        bodyIndex: 0,
        isPrimary: false,
        sequenceIndex: 1,
      },
      {
        id: 'arm::wrist::0',
        componentId: 'arm',
        componentName: 'Arm Component',
        linkId: 'wrist',
        linkName: 'Wrist Link',
        objectIndex: 0,
        bodyIndex: null,
        isPrimary: true,
        sequenceIndex: 0,
      },
    ],
  );

  robot.links.base.collision!.dimensions.x = 99;
  assert.equal(targets[0].geometry.dimensions.x, 1);
});

test('filterCollisionTargets handles mesh, primitive, selected, and empty selected scopes', () => {
  const targets = collectCollisionTargets({ kind: 'robot', robot: createTargetRobot() });

  assert.deepEqual(
    filterCollisionTargets(targets, { scope: 'mesh' }).map((target) => target.id),
    ['robot::base::1'],
  );
  assert.deepEqual(
    filterCollisionTargets(targets, { scope: 'primitive' }).map((target) => target.id),
    ['robot::base::0', 'robot::wrist::0'],
  );
  assert.deepEqual(
    filterCollisionTargets(targets, { scope: 'selected', selectedTargetId: 'robot::wrist::0' }).map(
      (target) => target.id,
    ),
    ['robot::wrist::0'],
  );
  assert.deepEqual(filterCollisionTargets(targets, { scope: 'selected' }), []);
});

test('collision target helpers build ids, link group keys, deep clones, and finite normalized geometry', () => {
  const geometry = createCollisionGeometry('invalid', GeometryType.BOX, {
    dimensions: { x: Number.NaN, y: Infinity, z: 4 },
    origin: {
      xyz: { x: Number.NaN, y: 5, z: Infinity },
      rpy: { r: 1, p: Number.NaN, y: Infinity },
    },
  });

  const clone = cloneCollisionGeometry(geometry);
  clone.dimensions.z = 7;
  clone.origin.xyz.y = 8;

  assert.equal(geometry.dimensions.z, 4);
  assert.equal(geometry.origin.xyz.y, 5);
  assert.equal(createCollisionTargetId(undefined, 'base', 2), 'robot::base::2');
  assert.equal(createCollisionTargetId('arm', 'base', 2), 'arm::base::2');
  assert.equal(getCollisionTargetLinkGroupKey({ componentId: 'arm', linkId: 'base' }), 'arm::base');

  assert.deepEqual(normalizeCollisionGeometry(geometry), {
    ...geometry,
    dimensions: { x: 0, y: 0, z: 4 },
    origin: {
      xyz: { x: 0, y: 5, z: 0 },
      rpy: { r: 1, p: 0, y: 0 },
    },
  });
});
