import assert from 'node:assert/strict';
import test from 'node:test';

import { compareUnitreeRosUsdaBrowserPhysics } from './compare_unitree_ros_usda_browser_physics.mjs';

function browserLinkPose(linkName, position = [0, 0, 0], quaternion = [0, 0, 0, 1]) {
  return {
    linkId: linkName,
    linkName,
    position,
    quaternion,
    scale: [1, 1, 1],
  };
}

function browserReport(
  links,
  joints = [],
  nativeJoints = [],
  linkPoses = undefined,
  options = {},
) {
  const resolvedLinkPoses = linkPoses ?? links.map((link) => browserLinkPose(link.name ?? link.id));
  return {
    results: [
      {
        modelKey: 'go2_description/urdf/go2_description.usda',
        targetFileName: 'go2_description/urdf/go2_description.usda',
        selectedFileName: 'go2_description/urdf/go2_description.usda',
        snapshot: {
          store: {
            links,
            joints,
          },
          ...(options.snapshotRuntime ? { runtime: options.snapshotRuntime } : {}),
        },
        selectedUsdSceneSummary: {
          robotMetadata: {
            joints: nativeJoints,
          },
          linkPoses: {
            source: 'store-kinematics',
            storeLinkCount: resolvedLinkPoses.length,
            storeLinks: resolvedLinkPoses,
          },
          ...(options.collisionSummary ? { collisionSummary: options.collisionSummary } : {}),
        },
        ...(options.selectedUsdVisualMaterialSummary
          ? { selectedUsdVisualMaterialSummary: options.selectedUsdVisualMaterialSummary }
          : {}),
        ...(options.runtimeSceneTransforms
          ? { runtimeSceneTransforms: options.runtimeSceneTransforms }
          : {}),
      },
    ],
  };
}

function browserLink(id, mass, centerOfMass = [0, 0, 0], diagonalInertia = [0, 0, 0]) {
  return {
    id,
    name: id,
    mass,
    centerOfMass: {
      xyz: {
        x: centerOfMass[0],
        y: centerOfMass[1],
        z: centerOfMass[2],
      },
      rpy: {
        r: 0,
        p: 0,
        y: 0,
      },
    },
    inertia: {
      ixx: diagonalInertia[0],
      ixy: 0,
      ixz: 0,
      iyy: diagonalInertia[1],
      iyz: 0,
      izz: diagonalInertia[2],
    },
  };
}

function jointFrame(localPos0 = [0, 0, 0]) {
  return {
    localPos0,
    localRot0Wxyz: [1, 0, 0, 0],
    localPos1: [0, 0, 0],
    localRot1Wxyz: [1, 0, 0, 0],
  };
}

function browserJoint(name, frame = jointFrame()) {
  return {
    id: name,
    name,
    usdPhysics: frame,
  };
}

function nativeJoint(name, frame = jointFrame()) {
  return {
    jointName: name,
    ...frame,
  };
}

function truthJoint(name, frame = jointFrame()) {
  return {
    fullPath: `/go2_description/joints/${name}`,
    name,
    localPos0: frame.localPos0,
    localRot0: frame.localRot0Wxyz,
    localPos1: frame.localPos1,
    localRot1: frame.localRot1Wxyz,
  };
}

function truthReport(rigidBodies, joints = {}) {
  return {
    'test/unitree_ros_usda/go2_description/urdf/go2_description.usda': {
      open_ok: true,
      rigidBodies,
      joints,
    },
  };
}

function materialTruthReport(stage) {
  return {
    'test/unitree_ros_usda/go2_description/urdf/go2_description.usda': stage,
  };
}

function truthBody(
  name,
  mass,
  centerOfMass = [0, 0, 0],
  diagonalInertia = [0, 0, 0],
  worldPosition = [0, 0, 0],
  worldOrientationWxyz = [1, 0, 0, 0],
  collisionCount = 0,
) {
  return {
    fullPath: `/go2_description/${name}`,
    name,
    worldPose: {
      position: worldPosition,
      orientationWxyz: worldOrientationWxyz,
    },
    mass,
    centerOfMass,
    diagonalInertia,
    principalAxes: [1, 0, 0, 0],
    collisionCount,
  };
}

test('compareUnitreeRosUsdaBrowserPhysics passes exact mass, COM, inertia and joint frame parity', () => {
  const frame = jointFrame([0.0039635, 0, -0.044]);
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [
        browserLink('base', 6.921, [0.021112, 0, -0.005366], [0.14, 0.25, 0.36]),
        browserLink('FL_calf_rotor', 0.089, [0, 0, 0]),
      ],
      [browserJoint('head_joint', frame)],
      [nativeJoint('head_joint', frame)],
      [
        browserLinkPose('base', [0, 0, 0]),
        browserLinkPose('FL_calf_rotor', [0.18, 0.047, -0.2]),
      ],
    ),
    truthReport: truthReport(
      {
        '/base': truthBody('base', 6.921, [0.021112, 0, -0.005366], [0.14, 0.25, 0.36]),
        '/FL_calf_rotor': truthBody(
          'FL_calf_rotor',
          0.089,
          [0, 0, 0],
          [0, 0, 0],
          [0.18, 0.047, -0.2],
        ),
      },
      {
        '/joints/head_joint': truthJoint('head_joint', frame),
      },
    ),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.matchedLinks, 2);
  assert.equal(comparison.summary.matchedLinkPoses, 2);
  assert.equal(comparison.summary.matchedJoints, 1);
  assert.equal(comparison.summary.missingLinks, 0);
  assert.equal(comparison.summary.massMismatches, 0);
  assert.equal(comparison.summary.comMismatches, 0);
  assert.equal(comparison.summary.inertiaMismatches, 0);
  assert.equal(comparison.summary.linkPositionMismatches, 0);
  assert.equal(comparison.summary.linkOrientationMismatches, 0);
  assert.equal(comparison.summary.jointFrameMismatches, 0);
  assert.equal(comparison.summary.nativeJointFrameMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics compares collision counts per rigid body name', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 1)],
      [],
      [],
      undefined,
      {
        collisionSummary: {
          totalDescriptorCount: 2,
          linkCount: 1,
          links: [
            {
              linkPath: '/go2_description/base',
              linkName: 'base',
              descriptorCount: 2,
              primitiveTypes: {
                mesh: 2,
              },
            },
          ],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1, [0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 0, 0, 0], 2),
    }),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.browserCollisions, 2);
  assert.equal(comparison.summary.truthCollisions, 2);
  assert.equal(comparison.summary.collisionCountMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics prefers store collision counts over descriptors', () => {
  const link = browserLink('base', 1);
  link.collisionCount = 2;
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [link],
      [],
      [],
      undefined,
      {
        collisionSummary: {
          totalDescriptorCount: 0,
          linkCount: 0,
          links: [],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1, [0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 0, 0, 0], 2),
    }),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.browserCollisions, 2);
  assert.equal(comparison.summary.collisionCountMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics fails on collision count mismatch', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 1)],
      [],
      [],
      undefined,
      {
        collisionSummary: {
          totalDescriptorCount: 1,
          linkCount: 1,
          links: [
            {
              linkPath: '/go2_description/base',
              linkName: 'base',
              descriptorCount: 1,
              primitiveTypes: {
                mesh: 1,
              },
            },
          ],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1, [0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 0, 0, 0], 2),
    }),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.collisionCountMismatches, 1);
  assert.equal(comparison.failures[0]?.type, 'collision-count-mismatch');
});

test('compareUnitreeRosUsdaBrowserPhysics compares visible material appearance signatures', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 1)],
      [],
      [],
      undefined,
      {
        selectedUsdVisualMaterialSummary: {
          meshes: [
            {
              meshId: '/go2_description/base/visuals.proto_mesh_id0',
              linkPath: '/go2_description/base',
              materials: [
                {
                  materialId: '/Looks/Base',
                  colorTuple: [0.1, 0.2, 0.3],
                  textured: true,
                  textureCount: 1,
                  texturePaths: ['textures/base.png'],
                },
              ],
            },
          ],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1),
    }),
    materialTruthReport: materialTruthReport({
      open_ok: true,
      visibleAppearanceSignatures: [
        {
          color: [0.1005, 0.2005, 0.3005],
          textured: true,
        },
      ],
    }),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.browserMaterialAppearances, 1);
  assert.equal(comparison.summary.truthMaterialAppearances, 1);
  assert.equal(comparison.summary.materialAppearanceMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics falls back to runtime visual material signatures', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 1)],
      [],
      [],
      undefined,
      {
        snapshotRuntime: {
          visualMeshes: [
            {
              link: 'base',
              materials: [
                {
                  color: '#ffffff',
                  hasTexture: true,
                },
              ],
            },
          ],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1),
    }),
    materialTruthReport: materialTruthReport({
      open_ok: true,
      visibleAppearanceSignatures: [{ color: [1, 1, 1], textured: true }],
    }),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.browserTexturedMaterialAppearances, 1);
  assert.equal(comparison.summary.materialAppearanceMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics fails on material texture flag mismatch', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 1)],
      [],
      [],
      undefined,
      {
        selectedUsdVisualMaterialSummary: {
          meshes: [
            {
              meshId: '/go2_description/base/visuals.proto_mesh_id0',
              linkPath: '/go2_description/base',
              materials: [
                {
                  materialId: '/Looks/Base',
                  colorTuple: [0.1, 0.2, 0.3],
                  textured: false,
                  textureCount: 0,
                  texturePaths: [],
                },
              ],
            },
          ],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1),
    }),
    materialTruthReport: materialTruthReport({
      open_ok: true,
      visibleAppearanceSignatures: [
        {
          color: [0.1, 0.2, 0.3],
          textured: true,
        },
      ],
    }),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.materialAppearanceMismatches, 2);
  assert.equal(comparison.failures[0]?.type, 'material-appearance-mismatch');
});

test('compareUnitreeRosUsdaBrowserPhysics removes runtime viewer offset before world-position compare', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 1)],
      [],
      [],
      [browserLinkPose('base', [0, 0, 0])],
      {
        runtimeSceneTransforms: {
          links: [
            {
              name: 'base',
              position: [0, 0, 0.5],
            },
          ],
        },
      },
    ),
    truthReport: truthReport({
      '/base': truthBody('base', 1, [0, 0, 0], [0, 0, 0], [0, 0, 0]),
    }),
  });

  assert.equal(comparison.pass, true);
  assert.deepEqual(comparison.perModel[0]?.runtimeWorldPositionOffset, [0, 0, 0.5]);
  assert.equal(comparison.summary.worldPositionMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics skips parentless root fixed joints missing from store/native', () => {
  const rootJoint = truthJoint('rootJoint');
  rootJoint.type = 'PhysicsFixedJoint';
  rootJoint.body0Path = null;
  rootJoint.body0FullPath = null;
  rootJoint.body1Path = '/base';

  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('base', 1)]),
    truthReport: truthReport(
      {
        '/base': truthBody('base', 1),
      },
      {
        '/joints/rootJoint': rootJoint,
      },
    ),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.skippedBrowserRootJoints, 1);
  assert.equal(comparison.summary.skippedNativeRootJoints, 1);
  assert.equal(comparison.summary.missingBrowserJoints, 0);
  assert.equal(comparison.summary.missingNativeJoints, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics skips root joints anchored to one body', () => {
  const rootJoint = truthJoint('rootJoint');
  rootJoint.type = 'PhysicsJoint';
  rootJoint.body0Path = '/base';
  rootJoint.body0FullPath = '/robot/base';
  rootJoint.body1Path = null;
  rootJoint.body1FullPath = null;

  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('base', 1)]),
    truthReport: truthReport(
      {
        '/base': truthBody('base', 1),
      },
      {
        '/joints/rootJoint': rootJoint,
      },
    ),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.skippedBrowserRootJoints, 1);
  assert.equal(comparison.summary.skippedNativeRootJoints, 1);
  assert.equal(comparison.summary.missingBrowserJoints, 0);
  assert.equal(comparison.summary.missingNativeJoints, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics skips synthetic visual-only browser links', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([
      browserLink('base', 1),
      browserLink('visuals_proto_mesh_id1', 0, [0, 0, 0], [0.1, 0.1, 0.1]),
      browserLink('base__robot_visuals_mesh_1', 0, [0, 0, 0], [0.1, 0.1, 0.1]),
      browserLink('world', 0, [0, 0, 0], [0.1, 0.1, 0.1]),
    ]),
    truthReport: truthReport({
      '/base': truthBody('base', 1),
    }),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.extraLinks, 0);
  assert.equal(comparison.summary.skippedExtraVisualLinks, 3);
});

test('compareUnitreeRosUsdaBrowserPhysics fails when meshless physics links are missing', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('base', 6.921, [0.021112, 0, -0.005366])]),
    truthReport: truthReport({
      '/base': truthBody('base', 6.921, [0.021112, 0, -0.005366]),
      '/FL_calf_rotor': truthBody('FL_calf_rotor', 0.089, [0, 0, 0]),
    }),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.missingLinks, 1);
  assert.equal(comparison.failures[0]?.type, 'missing-browser-link');
  assert.equal(comparison.failures[0]?.link, 'FL_calf_rotor');
});

test('compareUnitreeRosUsdaBrowserPhysics treats missing MassAPI truth mass as zero', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('base', 1, [0, 0, 0])]),
    truthReport: truthReport({
      '/base': truthBody('base', null, null),
    }),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.massMismatches, 1);
  assert.equal(comparison.failures[0]?.type, 'mass-mismatch');
  assert.equal(comparison.failures[0]?.truthMass, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics fails on link-local COM drift', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('base', 6.921, [1.2, 0, -0.005366])]),
    truthReport: truthReport({
      '/base': truthBody('base', 6.921, [0.021112, 0, -0.005366]),
    }),
    comTolerance: 1e-6,
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.comMismatches, 1);
  assert.equal(comparison.failures[0]?.type, 'center-of-mass-mismatch');
});

test('compareUnitreeRosUsdaBrowserPhysics fails on diagonal inertia drift', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('base', 6.921, [0, 0, 0], [0.4, 0.2, 0.3])]),
    truthReport: truthReport({
      '/base': truthBody('base', 6.921, [0, 0, 0], [0.1, 0.2, 0.3]),
    }),
    inertiaTolerance: 1e-6,
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.inertiaMismatches, 1);
  assert.equal(comparison.failures[0]?.type, 'diagonal-inertia-mismatch');
});

test('compareUnitreeRosUsdaBrowserPhysics fails when store link pose is missing', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([browserLink('head_link', 1, [0, 0, 0])], [], [], []),
    truthReport: truthReport({
      '/head_link': truthBody('head_link', 1, [0, 0, 0], [0, 0, 0], [0.0039635, 0, -0.044]),
    }),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.missingBrowserLinkPoses, 1);
  assert.equal(comparison.failures[0]?.type, 'missing-browser-link-pose');
});

test('compareUnitreeRosUsdaBrowserPhysics fails on store link world-position drift', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('head_link', 1, [0, 0, 0])],
      [],
      [],
      [browserLinkPose('head_link', [0, 0, 0])],
    ),
    truthReport: truthReport({
      '/head_link': truthBody('head_link', 1, [0, 0, 0], [0, 0, 0], [0.0039635, 0, -0.044]),
    }),
    linkPositionTolerance: 1e-6,
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.linkPositionMismatches, 1);
  assert.equal(comparison.failures[0]?.type, 'link-position-mismatch');
});

test('compareUnitreeRosUsdaBrowserPhysics treats link orientation quaternion signs as equivalent', () => {
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('head_link', 1, [0, 0, 0])],
      [],
      [],
      [browserLinkPose('head_link', [0, 0, 0], [0, 0, 0, -1])],
    ),
    truthReport: truthReport({
      '/head_link': truthBody('head_link', 1, [0, 0, 0], [0, 0, 0], [0, 0, 0], [1, 0, 0, 0]),
    }),
    linkOrientationTolerance: 1e-6,
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.linkOrientationMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics treats zero truth principal axes as identity', () => {
  const sensorTruthBody = truthBody('imu_in_pelvis', 0, [0, 0, 0], [0.0001, 0.0001, 0.0001]);
  sensorTruthBody.principalAxes = [0, 0, 0, 0];

  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport([
      browserLink('imu_in_pelvis', 0, [0, 0, 0], [0.0001, 0.0001, 0.0001]),
    ]),
    truthReport: truthReport({
      '/imu_in_pelvis': sensorTruthBody,
    }),
  });

  assert.equal(comparison.pass, true);
  assert.equal(comparison.summary.principalAxesMismatches, 0);
});

test('compareUnitreeRosUsdaBrowserPhysics fails when native metadata omits a truth joint frame', () => {
  const frame = jointFrame([0.0039635, 0, -0.044]);
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 6.921)],
      [browserJoint('head_joint', frame)],
      [],
    ),
    truthReport: truthReport(
      {
        '/base': truthBody('base', 6.921),
      },
      {
        '/joints/head_joint': truthJoint('head_joint', frame),
      },
    ),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.missingNativeJoints, 1);
  assert.equal(comparison.failures[0]?.type, 'missing-native-joint');
});

test('compareUnitreeRosUsdaBrowserPhysics fails when native localPos0 drifts even if store is correct', () => {
  const truthFrame = jointFrame([0.0039635, 0, -0.044]);
  const nativeFrame = jointFrame([0, 0, 0]);
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport: browserReport(
      [browserLink('base', 6.921)],
      [browserJoint('head_joint', truthFrame)],
      [nativeJoint('head_joint', nativeFrame)],
    ),
    truthReport: truthReport(
      {
        '/base': truthBody('base', 6.921),
      },
      {
        '/joints/head_joint': truthJoint('head_joint', truthFrame),
      },
    ),
  });

  assert.equal(comparison.pass, false);
  assert.equal(comparison.summary.jointFrameMismatches, 0);
  assert.equal(comparison.summary.nativeJointFrameMismatches, 1);
  assert.equal(comparison.failures[0]?.type, 'native-joint-localPos0-mismatch');
});
