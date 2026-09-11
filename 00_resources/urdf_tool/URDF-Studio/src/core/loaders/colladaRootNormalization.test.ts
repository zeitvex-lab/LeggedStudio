import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

import { parseURDF } from '@/core/parsers/urdf/parser';
import { GeometryType, type UrdfLink } from '@/types';

import {
  buildColladaRootNormalizationHints,
  shouldNormalizeColladaRoot,
} from './colladaRootNormalization';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;

function parseRequiredURDF(content: string) {
  const robot = parseURDF(content);
  assert.ok(robot, 'expected URDF fixture to parse');
  return robot;
}

test('buildColladaRootNormalizationHints marks go2 Collada assets for normalization from URDF visual origins', () => {
  const urdfContent = fs.readFileSync('test/unitree_ros/robots/go2_description/urdf/go2_description.urdf', 'utf8');
  const robot = parseRequiredURDF(urdfContent);
  const hints = buildColladaRootNormalizationHints(robot.links);

  assert.ok(hints);
  assert.equal(shouldNormalizeColladaRoot('package://go2_description/dae/hip.dae', hints), true);
  assert.equal(shouldNormalizeColladaRoot('package://go2_description/meshes/dae/hip.dae', hints), true);
  assert.equal(shouldNormalizeColladaRoot('package://go2_description/dae/thigh.dae', hints), true);
  assert.equal(shouldNormalizeColladaRoot('package://go2_description/dae/calf_mirror.dae', hints), true);
});

test('buildColladaRootNormalizationHints leaves b2w Collada assets on raw loader path when URDF origins are identity', () => {
  const urdfContent = fs.readFileSync('test/unitree_ros/robots/b2w_description/urdf/b2w_description.urdf', 'utf8');
  const robot = parseRequiredURDF(urdfContent);
  const hints = buildColladaRootNormalizationHints(robot.links);

  assert.equal(shouldNormalizeColladaRoot('package://b2w_description/meshes/RL_thigh.dae', hints), false);
  assert.equal(shouldNormalizeColladaRoot('package://b2w_description/meshes/RR_calf.dae', hints), false);
});

test('buildColladaRootNormalizationHints ignores translation-only DAE origins', () => {
  const links = {
    base: {
      id: 'base',
      name: 'base',
      visible: true,
      visual: {
        name: 'base_visual',
        type: GeometryType.MESH,
        meshPath: 'package://demo_description/meshes/offset_only.dae',
        color: undefined,
        dimensions: { x: 1, y: 1, z: 1 },
        origin: {
          xyz: { x: 0.12, y: 0, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
        visible: true,
      },
      collision: {
        name: 'base_collision',
        type: GeometryType.NONE,
        dimensions: { x: 0, y: 0, z: 0 },
        origin: {
          xyz: { x: 0, y: 0, z: 0 },
          rpy: { r: 0, p: 0, y: 0 },
        },
        visible: true,
      },
      collisionBodies: [],
    } as unknown as UrdfLink,
  };

  const hints = buildColladaRootNormalizationHints(links);

  assert.equal(
    shouldNormalizeColladaRoot('package://demo_description/meshes/offset_only.dae', hints),
    false,
  );
});
