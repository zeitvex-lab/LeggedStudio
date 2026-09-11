import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { JSDOM } from 'jsdom';

import { DEFAULT_JOINT, DEFAULT_LINK, GeometryType, JointType, type RobotData } from '@/types';

import { computeRobotRenderableBoundsFromAssets } from './assemblyRenderableBounds.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;

function createMeshFallbackRobot(): RobotData {
  return {
    name: 'mesh_fallback_demo',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        ...DEFAULT_LINK,
        id: 'base_link',
        name: 'base_link',
        visible: true,
        visual: {
          ...DEFAULT_LINK.visual,
          type: GeometryType.BOX,
          dimensions: { x: 0.2, y: 0.2, z: 0.2 },
          origin: {
            xyz: { x: 0, y: 0, z: 0.05 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
        collision: {
          ...DEFAULT_LINK.collision,
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
        },
      },
      foot_link: {
        ...DEFAULT_LINK,
        id: 'foot_link',
        name: 'foot_link',
        visible: true,
        visual: {
          ...DEFAULT_LINK.visual,
          type: GeometryType.MESH,
          dimensions: { x: 1, y: 1, z: 1 },
          meshPath: 'robots/demo/missing-foot.stl',
        },
        collision: {
          ...DEFAULT_LINK.collision,
          type: GeometryType.BOX,
          dimensions: { x: 0.2, y: 0.2, z: 0.2 },
          origin: {
            xyz: { x: 0, y: 0, z: 0 },
            rpy: { r: 0, p: 0, y: 0 },
          },
        },
      },
    },
    joints: {
      foot_joint: {
        ...DEFAULT_JOINT,
        id: 'foot_joint',
        name: 'foot_joint',
        type: JointType.FIXED,
        parentLinkId: 'base_link',
        childLinkId: 'foot_link',
        origin: {
          xyz: { x: 0, y: 0, z: -0.8 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
    },
  };
}

test('computeRobotRenderableBoundsFromAssets tolerates unresolved mesh visuals and falls back to collision bounds', async () => {
  // Mesh visuals whose asset cannot be resolved (e.g. USD inline meshes whose
  // virtual .obj paths are never present in the asset pool) must not abort the
  // whole bounds computation. The unresolved visual is skipped, and bounds are
  // still derived from remaining geometry (here: base_link's box visual and
  // foot_link's box collision).
  const bounds = await computeRobotRenderableBoundsFromAssets(createMeshFallbackRobot(), {
    'robots/demo/placeholder.txt': 'data:text/plain,noop',
  });
  assert.ok(bounds, 'expected fallback bounds despite the unresolved mesh visual');
  assert.ok(bounds.min.x <= 0 && bounds.max.x >= 0, 'bounds should cover the base link');
});

test('computeRobotRenderableBoundsFromAssets resolves OBJ sidecar materials from text content when blob assets are incomplete', async () => {
  const robot: RobotData = {
    name: 'obj_sidecar_demo',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        ...DEFAULT_LINK,
        id: 'base_link',
        name: 'base_link',
        visible: true,
        visual: {
          ...DEFAULT_LINK.visual,
          type: GeometryType.MESH,
          dimensions: { x: 1, y: 1, z: 1 },
          meshPath: 'robot/assets/body.obj',
        },
      },
    },
    joints: {},
  };

  const bounds = await computeRobotRenderableBoundsFromAssets(
    robot,
    {
      'robot/assets/body.obj':
        'data:text/plain,mtllib%20body.mtl%0Ao%20Body%0Av%200%200%200%0Av%201%200%200%0Av%200%201%200%0Af%201%202%203',
    },
    {
      'robot/assets/body.obj': 'mtllib body.mtl\no Body\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3',
      'robot/assets/body.mtl': 'newmtl Body\nKd 1 0 0',
    },
  );

  assert.deepEqual(bounds, {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 1, y: 1, z: 0 },
  });
});

test('computeRobotRenderableBoundsFromAssets handles agilex piper mesh context built from fixture text sidecars', async () => {
  const fixtureRoot = path.resolve('test/mujoco_menagerie-main/agilex_piper');
  const piperXmlPath = path.join(fixtureRoot, 'piper.xml');
  const assetDir = path.join(fixtureRoot, 'assets');

  const piperXml = fs.readFileSync(piperXmlPath, 'utf8');
  const allFileContents: Record<string, string> = {
    'mujoco_menagerie-main/agilex_piper/piper.xml': piperXml,
  };
  const assets: Record<string, string> = {};

  for (const entry of fs.readdirSync(assetDir)) {
    const absolutePath = path.join(assetDir, entry);
    if (!fs.statSync(absolutePath).isFile()) {
      continue;
    }

    const virtualPath = `mujoco_menagerie-main/agilex_piper/assets/${entry}`;
    const lowerEntry = entry.toLowerCase();
    const fileBuffer = fs.readFileSync(absolutePath);
    if (lowerEntry.endsWith('.obj') || lowerEntry.endsWith('.mtl') || lowerEntry.endsWith('.dae')) {
      allFileContents[virtualPath] = fileBuffer.toString('utf8');
    }

    assets[virtualPath] = `data:application/octet-stream;base64,${fileBuffer.toString('base64')}`;
  }

  const mjcfFile = {
    name: 'mujoco_menagerie-main/agilex_piper/piper.xml',
    content: piperXml,
    format: 'mjcf' as const,
  };

  const { resolveRobotFileData } = await import('@/core/parsers/importRobotFile');
  const result = resolveRobotFileData(mjcfFile, {
    availableFiles: [mjcfFile],
    assets,
    allFileContents,
  });

  assert.equal(result.status, 'ready');
  if (result.status !== 'ready') {
    assert.fail('Expected agilex piper fixture to resolve');
  }

  const bounds = await computeRobotRenderableBoundsFromAssets(
    result.robotData,
    assets,
    allFileContents,
  );
  assert.ok(bounds);
});
