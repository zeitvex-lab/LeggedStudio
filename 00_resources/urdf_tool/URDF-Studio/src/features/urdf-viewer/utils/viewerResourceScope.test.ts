import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, type RobotFile, type UrdfLink } from '@/types';
import { encodeTextAssetAsDataUrl } from '@/core/loaders/textMeshAssetContext';

import {
  buildViewerRobotLinksScopeSignature,
  createStableViewerResourceScope,
  type ViewerResourceScope,
} from './viewerResourceScope';

const ZERO_ORIGIN = { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } };

function createMeshLink(meshPath: string): UrdfLink {
  return {
    id: 'base_link',
    name: 'base_link',
    visual: {
      type: GeometryType.MESH,
      meshPath,
      color: '#ffffff',
      dimensions: { x: 1, y: 1, z: 1 },
      origin: ZERO_ORIGIN,
    },
    collision: {
      type: GeometryType.MESH,
      meshPath,
      color: '#ffffff',
      dimensions: { x: 1, y: 1, z: 1 },
      origin: ZERO_ORIGIN,
    },
    inertial: undefined,
    visible: true,
    collisionBodies: [],
  };
}

function scope(
  previous: ViewerResourceScope | null,
  overrides: Partial<Parameters<typeof createStableViewerResourceScope>[1]> = {},
): ViewerResourceScope {
  return createStableViewerResourceScope(previous, {
    assets: {
      'robots/go1/meshes/base.dae': 'blob:go1-base',
      'robots/go1/materials/body.png': 'blob:go1-body',
      'robots/go2/meshes/base.dae': 'blob:go2-base',
    },
    availableFiles: [],
    sourceFile: {
      name: 'robots/go1/urdf/go1.urdf',
      content: '<robot name="go1" />',
      format: 'urdf',
    },
    sourceFilePath: 'robots/go1/urdf/go1.urdf',
    robotLinks: {
      base_link: createMeshLink('robots/go1/meshes/base.dae'),
    },
    ...overrides,
  });
}

test('createStableViewerResourceScope reuses the previous scope when unrelated assets are imported', () => {
  const initial = scope(null);

  const next = scope(initial, {
    assets: {
      'robots/go1/meshes/base.dae': 'blob:go1-base',
      'robots/go1/materials/body.png': 'blob:go1-body',
      'robots/go2/meshes/base.dae': 'blob:go2-base',
      'robots/go2/materials/body.png': 'blob:go2-body',
      'robots/h1/meshes/arm.stl': 'blob:h1-arm',
    },
  });

  assert.equal(next, initial);
  assert.deepEqual(next.assets, {
    'robots/go1/meshes/base.dae': 'blob:go1-base',
    'robots/go1/materials/body.png': 'blob:go1-body',
  });
});

test('buildViewerRobotLinksScopeSignature stays stable when mesh references do not change', () => {
  const initial = buildViewerRobotLinksScopeSignature({
    base_link: createMeshLink('robots/go1/meshes/base.dae'),
  });

  const next = buildViewerRobotLinksScopeSignature({
    base_link: {
      ...createMeshLink('robots/go1/meshes/base.dae'),
      visible: false,
      collisionBodies: [
        {
          type: GeometryType.BOX,
          dimensions: { x: 1, y: 1, z: 1 },
          origin: ZERO_ORIGIN,
          color: '#ff0000',
        },
      ],
    },
  });

  assert.equal(next, initial);
});

test('createStableViewerResourceScope updates the scope when a relevant asset changes', () => {
  const initial = scope(null);

  const next = scope(initial, {
    assets: {
      'robots/go1/meshes/base.dae': 'blob:go1-base-v2',
      'robots/go1/materials/body.png': 'blob:go1-body',
      'robots/go2/meshes/base.dae': 'blob:go2-base',
    },
  });

  assert.notEqual(next, initial);
  assert.deepEqual(next.assets, {
    'robots/go1/meshes/base.dae': 'blob:go1-base-v2',
    'robots/go1/materials/body.png': 'blob:go1-body',
  });
});

test('createStableViewerResourceScope keeps texture assets referenced by merged workspace materials without a source file', () => {
  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'snowman/meshes/body.dae': 'blob:snowman-body',
      'snowman/materials/textures/coat.png': 'blob:snowman-coat',
      'g1/meshes/pelvis.dae': 'blob:g1-pelvis',
      'robots/go1/meshes/base.dae': 'blob:go1-base',
    },
    availableFiles: [],
    robotLinks: {
      snowman_base: createMeshLink('snowman/meshes/body.dae'),
      g1_base: createMeshLink('g1/meshes/pelvis.dae'),
    },
    robotMaterials: {
      snowman_base: {
        texture: 'snowman/materials/textures/coat.png',
      },
    },
  });

  assert.deepEqual(scoped.assets, {
    'snowman/meshes/body.dae': 'blob:snowman-body',
    'snowman/materials/textures/coat.png': 'blob:snowman-coat',
    'g1/meshes/pelvis.dae': 'blob:g1-pelvis',
  });
});

test('createStableViewerResourceScope includes textures referenced by scoped OBJ MTL sidecars', () => {
  const materialContent = [
    'newmtl CardboardBoxes',
    'Kd 1 1 1',
    'map_Kd ../materials/textures/cardboard_box.png',
  ].join('\n');

  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'obj_mtl_regression/meshes/body.obj': 'blob:body-obj',
      'obj_mtl_regression/materials/textures/cardboard_box.png': 'blob:cardboard-texture',
      'other/materials/textures/cardboard_box.png': 'blob:other-texture',
    },
    allFileContents: {
      'obj_mtl_regression/meshes/body.mtl': materialContent,
    },
    availableFiles: [],
    sourceFile: {
      name: 'obj_mtl_regression/robot.urdf',
      content: '<robot name="obj_mtl_regression" />',
      format: 'urdf',
    },
    sourceFilePath: 'obj_mtl_regression/robot.urdf',
    robotLinks: {
      base_link: createMeshLink('obj_mtl_regression/meshes/body.obj'),
    },
  });

  assert.deepEqual(scoped.assets, {
    'obj_mtl_regression/meshes/body.obj': 'blob:body-obj',
    'obj_mtl_regression/meshes/body.mtl': encodeTextAssetAsDataUrl(materialContent),
    'obj_mtl_regression/materials/textures/cardboard_box.png': 'blob:cardboard-texture',
  });
});

test('createStableViewerResourceScope reuses the previous USD scope when unrelated bundle files are added', () => {
  const sourceFile: RobotFile = {
    name: 'robots/go2/usd/go2.usd',
    content: '',
    format: 'usd',
    blobUrl: 'blob:go2-root',
  };

  const initial = createStableViewerResourceScope(null, {
    assets: {
      'robots/go2/usd/go2.usd': 'blob:go2-root',
      'robots/go2/usd/configuration/base.usd': 'blob:go2-base',
      'robots/h1/usd/h1.usd': 'blob:h1-root',
    },
    availableFiles: [
      sourceFile,
      {
        name: 'robots/go2/usd/configuration/base.usd',
        content: '',
        format: 'usd',
        blobUrl: 'blob:go2-base',
      },
      {
        name: 'robots/h1/usd/h1.usd',
        content: '',
        format: 'usd',
        blobUrl: 'blob:h1-root',
      },
    ],
    sourceFile,
  });

  const next = createStableViewerResourceScope(initial, {
    assets: {
      'robots/go2/usd/go2.usd': 'blob:go2-root',
      'robots/go2/usd/configuration/base.usd': 'blob:go2-base',
      'robots/h1/usd/h1.usd': 'blob:h1-root',
      'robots/h1/usd/configuration/base.usd': 'blob:h1-base',
    },
    availableFiles: [
      sourceFile,
      {
        name: 'robots/go2/usd/configuration/base.usd',
        content: '',
        format: 'usd',
        blobUrl: 'blob:go2-base',
      },
      {
        name: 'robots/h1/usd/h1.usd',
        content: '',
        format: 'usd',
        blobUrl: 'blob:h1-root',
      },
      {
        name: 'robots/h1/usd/configuration/base.usd',
        content: '',
        format: 'usd',
        blobUrl: 'blob:h1-base',
      },
    ],
    sourceFile,
  });

  assert.equal(next, initial);
  assert.deepEqual(
    next.availableFiles.map((file) => file.name),
    ['robots/go2/usd/go2.usd', 'robots/go2/usd/configuration/base.usd'],
  );
});

test('createStableViewerResourceScope includes top-level sibling mesh folders for root-level URDF bundles before robot links stabilize', () => {
  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'urdf/b2w_description.urdf': 'blob:b2w-urdf',
      'meshes/RR_thigh.dae': 'blob:rr-thigh',
      'materials/b2w.png': 'blob:b2w-material',
      'robots/go1/meshes/base.dae': 'blob:go1-base',
    },
    availableFiles: [],
    sourceFile: {
      name: 'urdf/b2w_description.urdf',
      content: '<robot name="b2w" />',
      format: 'urdf',
    },
    sourceFilePath: 'urdf/b2w_description.urdf',
    robotLinks: {},
  });

  assert.deepEqual(scoped.assets, {
    'urdf/b2w_description.urdf': 'blob:b2w-urdf',
    'meshes/RR_thigh.dae': 'blob:rr-thigh',
    'materials/b2w.png': 'blob:b2w-material',
  });
});

test('createStableViewerResourceScope recognizes duplicate-suffixed top-level bundle folders from collision renames', () => {
  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'urdf (1)/b2w_description.urdf': 'blob:b2w-urdf',
      'meshes (1)/RR_thigh.dae': 'blob:rr-thigh',
      'textures (1)/b2w.png': 'blob:b2w-texture',
      'robots/go1/meshes/base.dae': 'blob:go1-base',
    },
    availableFiles: [],
    sourceFile: {
      name: 'urdf (1)/b2w_description.urdf',
      content: '<robot name="b2w" />',
      format: 'urdf',
    },
    sourceFilePath: 'urdf (1)/b2w_description.urdf',
    robotLinks: {},
  });

  assert.deepEqual(scoped.assets, {
    'urdf (1)/b2w_description.urdf': 'blob:b2w-urdf',
    'meshes (1)/RR_thigh.dae': 'blob:rr-thigh',
    'textures (1)/b2w.png': 'blob:b2w-texture',
  });
});

test('createStableViewerResourceScope keeps sibling mesh assets for xml-based MJCF bundles before robot links stabilize', () => {
  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'robots/b2_description_mujoco/xml/b2.xml': 'blob:b2-xml',
      'robots/b2_description_mujoco/xml/scene.xml': 'blob:b2-scene',
      'robots/b2_description_mujoco/meshes/base_link.obj': 'blob:b2-base',
      'robots/go1/meshes/base.dae': 'blob:go1-base',
    },
    availableFiles: [],
    sourceFile: {
      name: 'robots/b2_description_mujoco/xml/b2.xml',
      content: '<mujoco model="b2" />',
      format: 'mjcf',
    },
    sourceFilePath: 'robots/b2_description_mujoco/xml/b2.xml',
    robotLinks: {},
  });

  assert.deepEqual(scoped.assets, {
    'robots/b2_description_mujoco/xml/b2.xml': 'blob:b2-xml',
    'robots/b2_description_mujoco/xml/scene.xml': 'blob:b2-scene',
    'robots/b2_description_mujoco/meshes/base_link.obj': 'blob:b2-base',
  });
});

test('createStableViewerResourceScope scopes broad MJCF scanned-object libraries to the selected model folder', () => {
  const assets: Record<string, string> = {};
  for (let index = 0; index < 2200; index += 1) {
    assets[`mujoco_scanned_objects/models/object_${index}/model.obj`] = `blob:other-${index}`;
    assets[`mujoco_scanned_objects/models/object_${index}/texture.png`] =
      `blob:other-texture-${index}`;
  }

  assets['mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/model.obj'] = 'blob:model';
  assets['mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/model_collision_0.obj'] =
    'blob:collision';
  assets['mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/texture.png'] = 'blob:texture';

  const sourceFile: RobotFile = {
    name: 'mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/model.xml',
    content: `
      <mujoco model="model">
        <asset>
          <texture type="2d" name="texture" file="texture.png" />
          <mesh name="model" file="model.obj" />
          <mesh name="collision" file="model_collision_0.obj" />
        </asset>
      </mujoco>
    `,
    format: 'mjcf',
  };

  const scoped = createStableViewerResourceScope(null, {
    assets,
    availableFiles: [sourceFile],
    sourceFile,
    sourceFilePath: sourceFile.name,
    robotLinks: {},
  });

  assert.deepEqual(scoped.assets, {
    'mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/model.obj': 'blob:model',
    'mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/model_collision_0.obj':
      'blob:collision',
    'mujoco_scanned_objects/models/GEOMETRIC_PEG_BOARD/texture.png': 'blob:texture',
  });
});

test('createStableViewerResourceScope retains repo-rooted sibling package assets that the mesh loader can resolve', () => {
  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'halodi-robot-models/eve_r3_description/urdf/eve_r3_robotiq_2f_85.urdf': 'blob:eve-urdf',
      'halodi-robot-models/robotiq_2f_85_gripper_visualization/meshes/visual/robotiq_arg2f_85_inner_knuckle.dae':
        'blob:visual-knuckle',
      'halodi-robot-models/robotiq_2f_85_gripper_visualization/meshes/collision/robotiq_arg2f_85_inner_knuckle.dae':
        'blob:collision-knuckle',
      'robots/go1/meshes/base.dae': 'blob:go1-base',
    },
    availableFiles: [],
    sourceFile: {
      name: 'halodi-robot-models/eve_r3_description/urdf/eve_r3_robotiq_2f_85.urdf',
      content: '<robot name="eve_r3" />',
      format: 'urdf',
    },
    sourceFilePath: 'halodi-robot-models/eve_r3_description/urdf/eve_r3_robotiq_2f_85.urdf',
    robotLinks: {
      gripper_link: createMeshLink(
        'package://robotiq_2f_85_gripper_visualization/meshes/visual/robotiq_arg2f_85_inner_knuckle.dae',
      ),
    },
  });

  assert.deepEqual(scoped.assets, {
    'halodi-robot-models/eve_r3_description/urdf/eve_r3_robotiq_2f_85.urdf': 'blob:eve-urdf',
    'halodi-robot-models/robotiq_2f_85_gripper_visualization/meshes/visual/robotiq_arg2f_85_inner_knuckle.dae':
      'blob:visual-knuckle',
  });
});

test('createStableViewerResourceScope keeps compiler-scoped MJCF sibling assets from included files before robot links stabilize', () => {
  const sourceFile: RobotFile = {
    name: 'myosuite-main/myosuite/envs/myo/assets/leg/myolegs_chasetag.xml',
    content: `
      <mujoco model="chasetag">
        <compiler meshdir="../../../../simhive/myo_sim/" texturedir="../../../../simhive/myo_sim/" />
        <include file="../../../../simhive/myo_sim/scene/myosuite_quad.xml" />
      </mujoco>
    `,
    format: 'mjcf',
  };

  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'myosuite-main/myosuite/envs/myo/assets/leg/myolegs_chasetag.xml': 'blob:chasetag',
      'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_quad.xml': 'blob:quad',
      'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_icon.png': 'blob:icon',
      'myosuite-main/myosuite/simhive/myo_sim/scene/floor0.png': 'blob:floor',
      'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_scene_noFloor_noPedestal.msh':
        'blob:scene',
      'robots/go1/meshes/base.dae': 'blob:go1-base',
    },
    availableFiles: [
      sourceFile,
      {
        name: 'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_quad.xml',
        content: `
          <mujoco model="quad-scene">
            <compiler angle="radian" meshdir=".." texturedir=".." />
            <asset>
              <texture name="icon" type="2d" file="scene/myosuite_icon.png" />
              <texture name="floor" type="2d" file="scene/floor0.png" />
              <mesh name="arena" file="../myo_sim/scene/myosuite_scene_noFloor_noPedestal.msh" />
              <mesh name="pyramid" vertex="0 0 0  0 1 0  0 0 1" />
            </asset>
          </mujoco>
        `,
        format: 'mjcf',
      },
    ],
    sourceFile,
    sourceFilePath: sourceFile.name,
    robotLinks: {},
  });

  assert.deepEqual(scoped.assets, {
    'myosuite-main/myosuite/envs/myo/assets/leg/myolegs_chasetag.xml': 'blob:chasetag',
    'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_quad.xml': 'blob:quad',
    'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_icon.png': 'blob:icon',
    'myosuite-main/myosuite/simhive/myo_sim/scene/floor0.png': 'blob:floor',
    'myosuite-main/myosuite/simhive/myo_sim/scene/myosuite_scene_noFloor_noPedestal.msh':
      'blob:scene',
  });
});

test('createStableViewerResourceScope merges MJCF OBJ sidecar text assets needed by the viewer runtime', () => {
  const sourceFile: RobotFile = {
    name: 'mujoco_menagerie-main/agilex_piper/piper.xml',
    format: 'mjcf',
    content: `
      <mujoco model="piper">
        <compiler meshdir="assets" />
        <asset>
          <mesh name="link3_12" file="link3_12.obj" />
        </asset>
      </mujoco>
    `,
  };

  const scoped = createStableViewerResourceScope(null, {
    assets: {
      'mujoco_menagerie-main/agilex_piper/assets/link3_12.obj': 'blob:obj',
    },
    availableFiles: [sourceFile],
    sourceFile,
    sourceFilePath: sourceFile.name,
    robotLinks: {},
    allFileContents: {
      'mujoco_menagerie-main/agilex_piper/assets/link3_12.obj': 'mtllib material.mtl',
      'mujoco_menagerie-main/agilex_piper/assets/material.mtl': 'newmtl demo\nKd 1 0 0',
    },
  });

  assert.deepEqual(scoped.assets, {
    'mujoco_menagerie-main/agilex_piper/assets/link3_12.obj': 'blob:obj',
    'mujoco_menagerie-main/agilex_piper/assets/material.mtl':
      encodeTextAssetAsDataUrl('newmtl demo\nKd 1 0 0'),
  });
});
