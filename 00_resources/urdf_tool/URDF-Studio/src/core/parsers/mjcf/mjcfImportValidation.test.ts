import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import type { RobotFile } from '@/types';
import { validateMJCFImportExternalAssets } from './mjcfImportValidation.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;

function createMjcfFile(name: string, content: string): RobotFile {
  return {
    name,
    content,
    format: 'mjcf',
  };
}

test('validateMJCFImportExternalAssets accepts runtime-resolvable myosuite arm mesh paths', () => {
  const content = `
    <mujoco>
      <compiler meshdir="../../../../simhive/myo_sim" />
      <asset>
        <mesh name="body_nohand" file="../myo_sim/meshes/human_lowpoly_nohand.stl" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/envs/myo/assets/arm/myoarm_bionic_bimanual.xml',
    content,
    [createMjcfFile('myosuite/simhive/myo_sim/arm/myoarm.xml', '<mujoco><worldbody /></mujoco>')],
    {
      'myosuite/simhive/myo_sim/meshes/human_lowpoly_nohand.stl': 'blob:human-lowpoly-nohand',
    },
  );

  assert.deepEqual(issues, []);
});

test('validateMJCFImportExternalAssets accepts runtime-resolvable duplicate-prefix paths', () => {
  const content = `
    <mujoco>
      <compiler meshdir="../../../../simhive/myo_sim" />
      <asset>
        <mesh name="tabletennis_table" file="../../envs/myo/assets/tabletennis_table.obj" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/envs/myo/assets/arm/myoarm_tabletennis.xml',
    content,
    [],
    {
      'myosuite/envs/myo/assets/tabletennis_table.obj': 'blob:tabletennis-table',
    },
  );

  assert.deepEqual(issues, []);
});

test('validateMJCFImportExternalAssets accepts compiler-normalized bundle paths', () => {
  const content = `
    <mujoco>
      <compiler meshdir="../../../../simhive/myo_sim" />
      <asset>
        <mesh name="tabletennis_table" file="../../envs/myo/assets/tabletennis_table.obj" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/envs/myo/assets/arm/myoarm_tabletennis.xml',
    content,
    [],
    {
      'myosuite/envs/myo/assets/tabletennis_table.obj': 'blob:tabletennis-table',
    },
  );

  assert.deepEqual(issues, []);
});

test('validateMJCFImportExternalAssets tolerates a single duplicated path segment after compiler normalization', () => {
  const content = `
    <mujoco>
      <compiler meshdir=".." />
      <asset>
        <mesh name="meshscene" file="../myo_sim/scene/myosuite_scene_noFloor.msh" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/simhive/myo_sim/scene/myosuite_scene.xml',
    content,
    [],
    {
      'myosuite/simhive/myo_sim/scene/myosuite_scene_noFloor.msh': 'blob:scene-msh',
    },
  );

  assert.deepEqual(issues, []);
});

test('validateMJCFImportExternalAssets resolves included assets against their scoped source file', () => {
  const content = `
    <mujoco>
      <asset data-urdf-studio-source-file="myosuite/simhive/myo_sim/scene/myosuite_scene.xml">
        <texture name="texfloor" type="2d" file="../myo_sim/scene/floor0.png" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/envs/myo/assets/arm/myoarm_relocate.xml',
    content,
    [
      createMjcfFile(
        'myosuite/simhive/myo_sim/scene/myosuite_scene.xml',
        '<mujoco><compiler meshdir=".." texturedir=".." /></mujoco>',
      ),
    ],
    {
      'myosuite/simhive/myo_sim/scene/floor0.png': 'blob:floor0',
    },
  );

  assert.deepEqual(issues, []);
});

test('validateMJCFImportExternalAssets uses expanded compiler directories for scene wrapper assets', () => {
  const content = `
    <mujoco>
      <compiler data-urdf-studio-source-file="robots/stretch/stretch.xml" assetdir="assets" />
      <asset>
        <texture name="wood" type="2d" file="wood.png" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'robots/stretch/scene.xml',
    content,
    [
      createMjcfFile('robots/stretch/scene.xml', '<mujoco><worldbody /></mujoco>'),
      createMjcfFile(
        'robots/stretch/stretch.xml',
        '<mujocoinclude><compiler assetdir="assets" /></mujocoinclude>',
      ),
    ],
    {
      'robots/stretch/assets/wood.png': 'blob:wood',
    },
  );

  assert.deepEqual(issues, []);
});

test('validateMJCFImportExternalAssets fuzzily rescues geometry asset path variants only', () => {
  const content = `
    <mujoco>
      <compiler meshdir="assets" />
      <include file="common.xml" />
      <asset>
        <mesh name="case_mesh" file="BASE_LINK.DAE" />
        <mesh name="file_mesh" file="file:///tmp/import/robot/meshes/arm.obj" />
        <mesh name="directory_mesh" file="meshes/leg.stl" />
        <mesh name="extension_mesh" file="legacy/foot.mesh" />
        <hfield name="height" file="terrain.raw" />
        <model name="nested_model" file="nested_model.xml" />
        <texture name="strict_texture" type="2d" file="textures/panel.png" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'robots/demo/scene.xml',
    content,
    [
      createMjcfFile('robots/demo/assets/models/nested_model.xml', '<mujoco><worldbody /></mujoco>'),
      createMjcfFile('robots/demo/assets/includes/common.xml', '<mujoco><worldbody /></mujoco>'),
    ],
    {
      'robots/demo/assets/meshes/base_link.dae': 'blob:base-link',
      'robots/demo/shared/arm.obj': 'blob:arm',
      'robots/demo/leg.stl': 'blob:leg',
      'robots/demo/assets/foot.dae': 'blob:foot',
      'robots/demo/assets/heightfields/terrain.raw': 'blob:terrain',
      'robots/demo/assets/materials/panel.png': 'blob:panel',
    },
  );

  assert.deepEqual(
    issues.map((issue) => [issue.referenceKind, issue.rawPath, issue.resolvedPath]),
    [
      ['include', 'common.xml', 'robots/demo/common.xml'],
      ['texture', 'textures/panel.png', 'robots/demo/textures/panel.png'],
    ],
  );
});

test('validateMJCFImportExternalAssets still reports genuinely missing external assets', () => {
  const content = `
    <mujoco>
      <asset>
        <mesh name="missing_mesh" file="../meshes/not-there.stl" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets('robots/demo/scene.xml', content, [], {});

  assert.equal(issues.length, 1);
  assert.equal(issues[0]?.referenceKind, 'mesh');
  assert.equal(issues[0]?.rawPath, '../meshes/not-there.stl');
  assert.equal(issues[0]?.resolvedPath, 'robots/meshes/not-there.stl');
});

test('validateMJCFImportExternalAssets does not rescue broken relative suffix matches', () => {
  const content = `
    <mujoco>
      <asset>
        <texture
          name="soccer_ball"
          type="cube"
          fileright="../../envs/myo/assets/leg_soccer/soccer_assets/soccer_scene/soccer_ball/right.png"
        />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/envs/myo/assets/leg_soccer/soccer_assets/soccer_scene/soccer_ball.xml',
    content,
    [],
    {
      'myosuite/envs/myo/assets/leg_soccer/soccer_assets/soccer_scene/soccer_ball/right.png':
        'blob:right-texture',
    },
  );

  assert.equal(issues.length, 1);
  assert.equal(issues[0]?.referenceKind, 'texture');
  assert.equal(
    issues[0]?.resolvedPath,
    'myosuite/envs/myo/assets/leg_soccer/envs/myo/assets/leg_soccer/soccer_assets/soccer_scene/soccer_ball/right.png',
  );
});

test('validateMJCFImportExternalAssets does not rescue approximate filename matches', () => {
  const content = `
    <mujoco>
      <asset>
        <mesh name="ping_pong_paddle_mesh" file="Ping_Pong_Paddle.obj" />
      </asset>
      <worldbody />
    </mujoco>
  `;

  const issues = validateMJCFImportExternalAssets(
    'myosuite/envs/myo/assets/paddle.xml',
    content,
    [],
    {
      'myosuite/envs/myo/assets/paddle.obj': 'blob:paddle-obj',
    },
  );

  assert.equal(issues.length, 1);
  assert.equal(issues[0]?.referenceKind, 'mesh');
  assert.equal(issues[0]?.resolvedPath, 'myosuite/envs/myo/assets/Ping_Pong_Paddle.obj');
});
