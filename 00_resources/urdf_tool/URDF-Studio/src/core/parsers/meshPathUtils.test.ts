import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  normalizeMeshPathForExport,
  normalizeTexturePathForExport,
  resolveMeshAssetUrl,
  resolveImportedAssetPath,
  rewriteRobotMeshPathsForSource,
  rewriteUrdfAssetPathsForExport,
} from './meshPathUtils';
import { GeometryType, type RobotData } from '@/types';

test('resolveImportedAssetPath keeps package assets rooted at the package name', () => {
  assert.equal(
    resolveImportedAssetPath(
      'package://scout_description/meshes/wheel.dae',
      'scout_description/urdf/scout_mini.urdf',
    ),
    'scout_description/meshes/wheel.dae',
  );
});

test('resolveImportedAssetPath maps deep package URIs to imported package-root candidates', () => {
  assert.equal(
    resolveImportedAssetPath(
      'package://drake/examples/pr2/models/pr2_description/meshes/base_v0/base.stl',
      'pr2_description/urdf/pr2_simplified.urdf',
      {
        candidateAssetPaths: [
          'pr2_description/urdf/pr2_simplified.urdf',
          'pr2_description/meshes/base_v0/base.stl',
        ],
      },
    ),
    'pr2_description/meshes/base_v0/base.stl',
  );
});

test('resolveImportedAssetPath uses source context to disambiguate deep package URI suffix matches', () => {
  assert.equal(
    resolveImportedAssetPath(
      'package://vendor/shared/pr2_description/meshes/base_v0/base.stl',
      'robots/right/pr2_description/urdf/pr2.urdf',
      {
        candidateAssetPaths: [
          'robots/left/pr2_description/meshes/base_v0/base.stl',
          'robots/right/pr2_description/meshes/base_v0/base.stl',
        ],
      },
    ),
    'robots/right/pr2_description/meshes/base_v0/base.stl',
  );
});

test('resolveImportedAssetPath keeps sdf model assets rooted at the model name', () => {
  assert.equal(
    resolveImportedAssetPath('model://bus_stop/meshes/base_link.dae', 'bus_stop/model.sdf'),
    'bus_stop/meshes/base_link.dae',
  );
});

test('resolveImportedAssetPath still resolves relative mesh paths against the source directory', () => {
  assert.equal(
    resolveImportedAssetPath('meshes/wheel.dae', 'scout_description/urdf/scout_mini.urdf'),
    'scout_description/urdf/meshes/wheel.dae',
  );
});

test('resolveImportedAssetPath preserves bundle-rooted asset paths beside source directories', () => {
  assert.equal(
    resolveImportedAssetPath(
      'pr2_description/meshes/base_v0/base.stl',
      'pr2_description/urdf/pr2_simplified.urdf',
    ),
    'pr2_description/meshes/base_v0/base.stl',
  );

  assert.equal(
    resolveImportedAssetPath('robots/demo/meshes/base.stl', 'robots/demo/urdf/demo.urdf'),
    'robots/demo/meshes/base.stl',
  );
});

test('resolveImportedAssetPath preserves deep parent traversal for myosuite-style MJCF asset paths', () => {
  assert.equal(
    resolveImportedAssetPath(
      '../../../../simhive/myo_sim/../myo_sim/meshes/humerus.stl',
      'myosuite-main/myosuite/envs/myo/assets/hand/myohand_pen.xml',
    ),
    'myosuite-main/myosuite/simhive/myo_sim/meshes/humerus.stl',
  );
});

test('normalizeTexturePathForExport strips package texture roots for zipped exports', () => {
  assert.equal(
    normalizeTexturePathForExport('package://go2_description/textures/body/coat.png'),
    'body/coat.png',
  );
});

test('normalizeTexturePathForExport keeps nested relative texture folders stable', () => {
  assert.equal(
    normalizeTexturePathForExport('./textures/pbr/base_color.png'),
    'pbr/base_color.png',
  );
});

test('normalizeMeshPathForExport strips imported package roots ahead of assets folders', () => {
  assert.equal(normalizeMeshPathForExport('ARX L5/assets/base_link.obj'), 'assets/base_link.obj');
});

test('normalizeMeshPathForExport strips absolute imported MJCF asset prefixes down to the package asset root', () => {
  assert.equal(
    normalizeMeshPathForExport(
      'home/xyk/Desktop/URDF-Studio/test/awesome_robot_descriptions_repos/mujoco_menagerie/unitree_go2/assets/base_0.obj',
    ),
    'assets/base_0.obj',
  );
});

test('normalizeTexturePathForExport strips absolute imported asset prefixes down to a stable package path', () => {
  assert.equal(
    normalizeTexturePathForExport(
      'home/xyk/Desktop/URDF-Studio/test/demo_robot/assets/albedo/base_color.png',
    ),
    'assets/albedo/base_color.png',
  );
});

test('resolveMeshAssetUrl fuzzily rescues common import and export mesh path variants', () => {
  const assets = {
    'shared/dae/base_link.dae': 'blob:base-dae',
    'robots/demo/assets/arm.obj': 'blob:arm-obj',
    'robots/demo/meshes/leg.stl': 'blob:leg-stl',
    'robots/demo/assets/foot.dae': 'blob:foot-dae',
  };

  assert.equal(
    resolveMeshAssetUrl('file:///tmp/import/shared/dae/base_link.dae', assets),
    'blob:base-dae',
  );
  assert.equal(
    resolveMeshAssetUrl('package://demo_description/meshes/ARM.OBJ', assets),
    'blob:arm-obj',
  );
  assert.equal(resolveMeshAssetUrl('robots\\demo\\mesh\\leg.stl', assets), 'blob:leg-stl');
  assert.equal(resolveMeshAssetUrl('legacy/foot.mesh', assets), 'blob:foot-dae');
});

test('rewriteRobotMeshPathsForSource stabilizes relative texture paths alongside meshes', () => {
  const robot: RobotData = {
    name: 'demo',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visual: {
          type: GeometryType.MESH,
          meshPath: '../meshes/base_link.dae',
          color: '#ffffff',
          authoredMaterials: [{ texture: './textures/panel.png' }],
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.MESH,
          meshPath: '../meshes/base_link.dae',
          color: '#ffffff',
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: undefined,
      },
    },
    joints: {},
    materials: {
      base_link: {
        texture: '../textures/paint.png',
      },
    },
  };

  const rewritten = rewriteRobotMeshPathsForSource(robot, 'robots/demo/urdf/demo.urdf');

  assert.equal(rewritten.links.base_link.visual.meshPath, 'robots/demo/meshes/base_link.dae');
  assert.equal(
    rewritten.links.base_link.visual.authoredMaterials?.[0]?.texture,
    'robots/demo/urdf/textures/panel.png',
  );
  assert.equal(rewritten.materials?.base_link?.texture, 'robots/demo/textures/paint.png');
});

test('rewriteRobotMeshPathsForSource preserves package-rooted texture paths that are already stable', () => {
  const robot: RobotData = {
    name: 'demo',
    rootLinkId: 'base_link',
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visual: {
          type: GeometryType.BOX,
          color: '#ffffff',
          authoredMaterials: [{ texture: 'demo/materials/textures/panel.png' }],
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.BOX,
          color: '#ffffff',
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: undefined,
      },
    },
    joints: {},
    materials: {
      base_link: {
        texture: 'demo/materials/textures/panel.png',
      },
    },
  };

  const rewritten = rewriteRobotMeshPathsForSource(robot, 'robots/demo/model.sdf');

  assert.equal(
    rewritten.links.base_link.visual.authoredMaterials?.[0]?.texture,
    'demo/materials/textures/panel.png',
  );
  assert.equal(rewritten.materials?.base_link?.texture, 'demo/materials/textures/panel.png');
});

test('rewriteRobotMeshPathsForSource preserves canonical cross-model SDF texture paths', () => {
  const robot: RobotData = {
    name: 'ambulance',
    rootLinkId: 'link',
    links: {
      link: {
        id: 'link',
        name: 'link',
        visual: {
          type: GeometryType.MESH,
          meshPath: 'ambulance/meshes/ambulance.obj',
          color: '#ffffff',
          authoredMaterials: [{ texture: 'suv/materials/textures/wheels_01.png' }],
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.BOX,
          color: '#ffffff',
          dimensions: { x: 1, y: 1, z: 1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: undefined,
      },
    },
    joints: {},
    materials: {
      link: {
        texture: 'suv/materials/textures/wheels_01.png',
      },
    },
  };

  const rewritten = rewriteRobotMeshPathsForSource(robot, 'ambulance/model.sdf');

  assert.equal(
    rewritten.links.link.visual.authoredMaterials?.[0]?.texture,
    'suv/materials/textures/wheels_01.png',
  );
  assert.equal(rewritten.materials?.link?.texture, 'suv/materials/textures/wheels_01.png');
});

test('rewriteUrdfAssetPathsForExport preserves go2 multi-material visuals while rewriting asset roots', () => {
  const source = fs.readFileSync(
    'test/unitree_ros/robots/go2_description/urdf/go2_description.urdf',
    'utf8',
  );

  const rewritten = rewriteUrdfAssetPathsForExport(source, {
    exportRobotName: 'go2_description',
  });

  assert.match(rewritten, /<mesh filename="package:\/\/go2_description\/meshes\/dae\/base\.dae"/);

  const baseVisual = rewritten.match(/<link name="base">[\s\S]*?<visual>([\s\S]*?)<\/visual>/);
  assert.ok(baseVisual);
  assert.equal((baseVisual[1].match(/<material\b/g) || []).length, 5);
});
