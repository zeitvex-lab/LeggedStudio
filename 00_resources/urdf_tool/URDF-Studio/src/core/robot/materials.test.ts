import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, type RobotData } from '@/types';
import { syncRobotMaterialsForLinkUpdate, syncRobotVisualColorsFromMaterials } from './materials';

test('syncRobotVisualColorsFromMaterials preserves additional visual body colors and collision bodies', () => {
  const robot: RobotData = {
    name: 'so100',
    rootLinkId: 'base',
    materials: {
      base: {
        color: '#ffd11e',
      },
    },
    links: {
      base: {
        id: 'base',
        name: 'base',
        visual: {
          type: GeometryType.MESH,
          meshPath: 'assets/Base.stl',
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#ffd11e',
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
        visualBodies: [
          {
            type: GeometryType.MESH,
            meshPath: 'assets/Base_Motor.stl',
            dimensions: { x: 1, y: 1, z: 1 },
            color: '#1a1a1a',
            origin: {
              xyz: { x: 0, y: 0, z: 0 },
              rpy: { r: 0, p: 0, y: 0 },
            },
          },
        ],
        collision: {
          type: GeometryType.MESH,
          meshPath: 'assets/Base.stl',
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#ffd11e',
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
        collisionBodies: [
          {
            type: GeometryType.MESH,
            meshPath: 'assets/Base_Motor.stl',
            dimensions: { x: 1, y: 1, z: 1 },
            color: '#1a1a1a',
            origin: {
              xyz: { x: 0, y: 0, z: 0 },
              rpy: { r: 0, p: 0, y: 0 },
            },
          },
        ],
      },
    },
    joints: {},
  };

  const normalized = syncRobotVisualColorsFromMaterials(robot);

  assert.equal(normalized.links.base.visual.color, '#ffd11e');
  assert.equal(normalized.links.base.visualBodies?.[0]?.color, '#1a1a1a');
  assert.equal(normalized.links.base.collision.meshPath, 'assets/Base.stl');
  assert.equal(normalized.links.base.collisionBodies?.[0]?.meshPath, 'assets/Base_Motor.stl');
});

test('syncRobotVisualColorsFromMaterials still syncs the primary visual color from robot materials', () => {
  const robot: RobotData = {
    name: 'single_visual',
    rootLinkId: 'base_link',
    materials: {
      base_link: {
        color: '#123456',
      },
    },
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visual: {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#abcdef',
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
        collision: {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#123456',
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
      },
    },
    joints: {},
  };

  const normalized = syncRobotVisualColorsFromMaterials(robot);

  assert.equal(normalized.links.base_link.visual.color, '#123456');
});

test('syncRobotVisualColorsFromMaterials does not collapse multi-material visuals to a tracked link color', () => {
  const robot: RobotData = {
    name: 'multi_visual',
    rootLinkId: 'base_link',
    materials: {
      base_link: {
        color: '#e0e0e0',
      },
    },
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visual: {
          type: GeometryType.MESH,
          meshPath: 'meshes/base_link.dae',
          dimensions: { x: 1, y: 1, z: 1 },
          color: '#ffffff',
          authoredMaterials: [
            { name: 'body', color: '#d3d7d3' },
            { name: 'accent_dark', color: '#000000' },
            { name: 'accent_trim', color: '#090909' },
          ],
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
        collision: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#000000',
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
      },
    },
    joints: {},
  };

  const normalized = syncRobotVisualColorsFromMaterials(robot);

  assert.equal(normalized.links.base_link.visual.color, undefined);
  assert.deepEqual(
    normalized.links.base_link.visual.authoredMaterials?.map((material) => material.color),
    ['#d3d7d3', '#000000', '#090909'],
  );
});

test('syncRobotMaterialsForLinkUpdate promotes primary visual texture edits into robot materials', () => {
  const nextMaterials = syncRobotMaterialsForLinkUpdate(
    {
      base_link: {
        color: '#0e0e10',
        texture: 'textures/legacy.png',
        usdMaterial: {
          mapPath: 'textures/legacy.png',
          roughness: 0.6,
        },
      },
    },
    {
      id: 'base_link',
      name: 'base_link',
      visual: {
        type: GeometryType.MESH,
        meshPath: 'meshes/base_link.stl',
        dimensions: { x: 1, y: 1, z: 1 },
        color: '#0e0e10',
        authoredMaterials: [{ texture: 'textures/updated.png' }],
        origin: {
          xyz: { x: 0, y: 0, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
      collision: {
        type: GeometryType.NONE,
        dimensions: { x: 0, y: 0, z: 0 },
        color: '#000000',
        origin: {
          xyz: { x: 0, y: 0, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
    },
  );

  assert.deepEqual(nextMaterials, {
    base_link: {
      color: '#0e0e10',
      texture: 'textures/updated.png',
    },
  });
});

test('syncRobotMaterialsForLinkUpdate clears stale textures when a primary visual falls back to color-only material', () => {
  const nextMaterials = syncRobotMaterialsForLinkUpdate(
    {
      base_link: {
        color: '#0e0e10',
        texture: 'textures/stale.png',
      },
    },
    {
      id: 'base_link',
      name: 'base_link',
      visual: {
        type: GeometryType.MESH,
        meshPath: 'meshes/base_link.stl',
        dimensions: { x: 1, y: 1, z: 1 },
        color: '#12ab34',
        origin: {
          xyz: { x: 0, y: 0, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
      collision: {
        type: GeometryType.NONE,
        dimensions: { x: 0, y: 0, z: 0 },
        color: '#000000',
        origin: {
          xyz: { x: 0, y: 0, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
    },
  );

  assert.deepEqual(nextMaterials, {
    base_link: {
      color: '#12ab34',
    },
  });
});
