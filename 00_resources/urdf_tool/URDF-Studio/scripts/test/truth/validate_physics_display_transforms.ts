import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { JSDOM } from 'jsdom';
import * as THREE from 'three';

import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { buildRuntimeRobotFromState } from '@/core/parsers/urdf/loader/buildRuntimeRobotFromState';
import {
  computeLinkWorldMatrices,
  getCollisionGeometryEntries,
  getVisualGeometryEntries,
} from '@/core/robot';
import { createOriginMatrix } from '@/core/robot/kinematics';
import { getRobotSceneNodeIndex } from '@/features/urdf-viewer/utils/robotSceneNodeIndex';
import {
  syncInertiaVisualizationForLinks,
  syncJointAxesVisualizationForJoints,
  syncOriginAxesVisualizationForLinks,
} from '@/features/urdf-viewer/utils/visualizationObjectSync';
import { hydrateUsdViewerRobotResolutionFromRuntime } from '@/features/urdf-viewer/utils/usdRuntimeRobotHydration';
import { adaptUsdViewerSnapshotToRobotData } from '@/features/urdf-viewer/utils/usdViewerRobotAdapter';
import {
  GeometryType,
  JointType,
  type RobotData,
  type RobotFile,
  type UrdfInertial,
  type UrdfJoint,
  type UrdfVisual,
  type UsdSceneMeshDescriptor,
  type UsdSceneSnapshot,
  type Vector3,
} from '@/types';

type TestCaseId = 'mujoco' | 'urdf' | 'xacro' | 'sdf' | 'usd' | 'usda';
type ImportFormat = Exclude<TestCaseId, 'mujoco' | 'usda'> | 'mjcf';

interface PoseTruth {
  xyz: Vector3;
  rpy: { r: number; p: number; y: number };
}

interface GeometryTruth {
  type: GeometryType;
  dimensions: Vector3;
  origin: PoseTruth;
  color?: string;
  materialName?: string;
}

interface LinkTruth {
  inertial: Required<Pick<UrdfInertial, 'mass' | 'origin' | 'inertia'>>;
  visual: GeometryTruth;
  collisions: GeometryTruth[];
}

interface JointTruth {
  id: string;
  type: JointType;
  parentLinkId: string;
  childLinkId: string;
  origin: PoseTruth;
  axis: Vector3;
  limit: { lower: number; upper: number; effort: number; velocity: number };
  dynamics: { damping: number; friction: number };
}

interface CaseDefinition {
  id: TestCaseId;
  sourceLabel: string;
  loadRobotData: () => RobotData;
}

interface CheckRecord {
  name: string;
  pass: boolean;
  message?: string;
}

interface CaseReport {
  id: TestCaseId;
  sourceLabel: string;
  pass: boolean;
  checkCount: number;
  failCount: number;
  checks: CheckRecord[];
}

interface ValidationReport {
  generatedAt: string;
  caseCount: number;
  passCount: number;
  failCount: number;
  checkCount: number;
  cases: CaseReport[];
}

const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/physics-display-transforms.json');
const POSITION_TOLERANCE = 1e-6;
const ROTATION_TOLERANCE = 1e-6;
const BASE_VISUAL_COLOR = '#6699cc';
const CHILD_VISUAL_COLOR = '#cc6633';
const BASE_VISUAL_RGBA = '0.4 0.6 0.8 1';
const CHILD_VISUAL_RGBA = '0.8 0.4 0.2 1';

const JOINT_TRUTH: JointTruth = {
  id: 'base_to_child',
  type: JointType.REVOLUTE,
  parentLinkId: 'base_link',
  childLinkId: 'child_link',
  origin: pose(0.4, -0.2, 0.3, 0.25),
  axis: { x: 0, y: 1, z: 0 },
  limit: { lower: -1, upper: 1, effort: 10, velocity: 2 },
  dynamics: { damping: 0.7, friction: 0.05 },
};

const LINK_TRUTH: Record<'base_link' | 'child_link', LinkTruth> = {
  base_link: {
    inertial: {
      mass: 2.5,
      origin: pose(0.07, 0.08, 0.09, 0.35),
      inertia: { ixx: 0.21, ixy: 0.01, ixz: 0.02, iyy: 0.31, iyz: 0.03, izz: 0.41 },
    },
    visual: {
      type: GeometryType.BOX,
      dimensions: { x: 0.4, y: 0.2, z: 0.1 },
      origin: pose(0.11, -0.02, 0.03, 0.1),
      color: BASE_VISUAL_COLOR,
      materialName: 'base_paint',
    },
    collisions: [
      {
        type: GeometryType.BOX,
        dimensions: { x: 0.3, y: 0.24, z: 0.16 },
        origin: pose(-0.04, 0.05, 0.06, -0.15),
      },
    ],
  },
  child_link: {
    inertial: {
      mass: 1.2,
      origin: pose(0.01, -0.02, 0.03, -0.3),
      inertia: { ixx: 0.11, ixy: 0.004, ixz: 0.005, iyy: 0.12, iyz: 0.006, izz: 0.13 },
    },
    visual: {
      type: GeometryType.BOX,
      dimensions: { x: 0.2, y: 0.16, z: 0.12 },
      origin: pose(-0.08, 0.04, 0.05, -0.05),
      color: CHILD_VISUAL_COLOR,
      materialName: 'child_paint',
    },
    collisions: [
      {
        type: GeometryType.BOX,
        dimensions: { x: 0.18, y: 0.14, z: 0.1 },
        origin: pose(0.02, 0.03, -0.04, 0.22),
      },
      {
        type: GeometryType.BOX,
        dimensions: { x: 0.1, y: 0.08, z: 0.06 },
        origin: pose(-0.03, -0.06, 0.07, -0.18),
      },
    ],
  },
};

function pose(x: number, y: number, z: number, yaw = 0): PoseTruth {
  return {
    xyz: { x, y, z },
    rpy: { r: 0, p: 0, y: yaw },
  };
}

function poseText(value: PoseTruth): string {
  return `${value.xyz.x} ${value.xyz.y} ${value.xyz.z} ${value.rpy.r} ${value.rpy.p} ${value.rpy.y}`;
}

function xyzText(value: PoseTruth): string {
  return `${value.xyz.x} ${value.xyz.y} ${value.xyz.z}`;
}

function rpyText(value: PoseTruth): string {
  return `${value.rpy.r} ${value.rpy.p} ${value.rpy.y}`;
}

function mjcfBoxHalfSizeText(): string {
  return '0.2 0.1 0.05';
}

function installDomGlobals(): void {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    contentType: 'text/html',
  });
  globalThis.window = dom.window as typeof globalThis.window;
  globalThis.document = dom.window.document as typeof globalThis.document;
  globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
  globalThis.Node = dom.window.Node as typeof Node;
  globalThis.Element = dom.window.Element as typeof Element;
  globalThis.Document = dom.window.Document as typeof Document;
  globalThis.self = globalThis;
}

function createUrdfSource(robotName: string, xacro = false): string {
  const propertyPrefix = xacro
    ? [
        '  <xacro:property name="base_mass" value="2.5" />',
        '  <xacro:property name="child_mass" value="1.2" />',
        '  <xacro:property name="joint_xyz" value="0.4 -0.2 0.3" />',
      ].join('\n')
    : '';
  const robotOpen = xacro
    ? `<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="${robotName}">`
    : `<robot name="${robotName}">`;
  const baseMass = xacro ? '${base_mass}' : String(LINK_TRUTH.base_link.inertial.mass);
  const childMass = xacro ? '${child_mass}' : String(LINK_TRUTH.child_link.inertial.mass);
  const jointXyz = xacro ? '${joint_xyz}' : xyzText(JOINT_TRUTH.origin);

  return `<?xml version="1.0"?>
${robotOpen}
${propertyPrefix}
  <material name="base_paint">
    <color rgba="${BASE_VISUAL_RGBA}" />
  </material>
  <material name="child_paint">
    <color rgba="${CHILD_VISUAL_RGBA}" />
  </material>
  <link name="base_link">
    <inertial>
      <origin xyz="${xyzText(LINK_TRUTH.base_link.inertial.origin)}" rpy="${rpyText(LINK_TRUTH.base_link.inertial.origin)}" />
      <mass value="${baseMass}" />
      <inertia ixx="0.21" ixy="0.01" ixz="0.02" iyy="0.31" iyz="0.03" izz="0.41" />
    </inertial>
    <visual name="base_visual">
      <origin xyz="${xyzText(LINK_TRUTH.base_link.visual.origin)}" rpy="${rpyText(LINK_TRUTH.base_link.visual.origin)}" />
      <geometry><box size="0.4 0.2 0.1" /></geometry>
      <material name="base_paint" />
    </visual>
    <collision name="base_collision">
      <origin xyz="${xyzText(LINK_TRUTH.base_link.collisions[0].origin)}" rpy="${rpyText(LINK_TRUTH.base_link.collisions[0].origin)}" />
      <geometry><box size="0.3 0.24 0.16" /></geometry>
    </collision>
  </link>
  <link name="child_link">
    <inertial>
      <origin xyz="${xyzText(LINK_TRUTH.child_link.inertial.origin)}" rpy="${rpyText(LINK_TRUTH.child_link.inertial.origin)}" />
      <mass value="${childMass}" />
      <inertia ixx="0.11" ixy="0.004" ixz="0.005" iyy="0.12" iyz="0.006" izz="0.13" />
    </inertial>
    <visual name="child_visual">
      <origin xyz="${xyzText(LINK_TRUTH.child_link.visual.origin)}" rpy="${rpyText(LINK_TRUTH.child_link.visual.origin)}" />
      <geometry><box size="0.2 0.16 0.12" /></geometry>
      <material name="child_paint" />
    </visual>
    <collision name="child_collision_primary">
      <origin xyz="${xyzText(LINK_TRUTH.child_link.collisions[0].origin)}" rpy="${rpyText(LINK_TRUTH.child_link.collisions[0].origin)}" />
      <geometry><box size="0.18 0.14 0.1" /></geometry>
    </collision>
    <collision name="child_collision_secondary">
      <origin xyz="${xyzText(LINK_TRUTH.child_link.collisions[1].origin)}" rpy="${rpyText(LINK_TRUTH.child_link.collisions[1].origin)}" />
      <geometry><box size="0.1 0.08 0.06" /></geometry>
    </collision>
  </link>
  <joint name="${JOINT_TRUTH.id}" type="revolute">
    <parent link="${JOINT_TRUTH.parentLinkId}" />
    <child link="${JOINT_TRUTH.childLinkId}" />
    <origin xyz="${jointXyz}" rpy="${rpyText(JOINT_TRUTH.origin)}" />
    <axis xyz="${JOINT_TRUTH.axis.x} ${JOINT_TRUTH.axis.y} ${JOINT_TRUTH.axis.z}" />
    <limit lower="-1" upper="1" effort="10" velocity="2" />
    <dynamics damping="${JOINT_TRUTH.dynamics.damping}" friction="${JOINT_TRUTH.dynamics.friction}" />
  </joint>
</robot>`;
}

function createSdfSource(): string {
  return `<?xml version="1.0"?>
<sdf version="1.6">
  <model name="sdf_display_probe">
    <link name="base_link">
      <inertial>
        <pose>${poseText(LINK_TRUTH.base_link.inertial.origin)}</pose>
        <mass>${LINK_TRUTH.base_link.inertial.mass}</mass>
        <inertia>
          <ixx>0.21</ixx><ixy>0.01</ixy><ixz>0.02</ixz>
          <iyy>0.31</iyy><iyz>0.03</iyz><izz>0.41</izz>
        </inertia>
      </inertial>
      <visual name="base_visual">
        <pose>${poseText(LINK_TRUTH.base_link.visual.origin)}</pose>
        <geometry><box><size>0.4 0.2 0.1</size></box></geometry>
        <material>
          <diffuse>${BASE_VISUAL_RGBA}</diffuse>
        </material>
      </visual>
      <collision name="base_collision">
        <pose>${poseText(LINK_TRUTH.base_link.collisions[0].origin)}</pose>
        <geometry><box><size>0.3 0.24 0.16</size></box></geometry>
      </collision>
    </link>
    <link name="child_link">
      <pose>${poseText(JOINT_TRUTH.origin)}</pose>
      <inertial>
        <pose>${poseText(LINK_TRUTH.child_link.inertial.origin)}</pose>
        <mass>${LINK_TRUTH.child_link.inertial.mass}</mass>
        <inertia>
          <ixx>0.11</ixx><ixy>0.004</ixy><ixz>0.005</ixz>
          <iyy>0.12</iyy><iyz>0.006</iyz><izz>0.13</izz>
        </inertia>
      </inertial>
      <visual name="child_visual">
        <pose>${poseText(LINK_TRUTH.child_link.visual.origin)}</pose>
        <geometry><box><size>0.2 0.16 0.12</size></box></geometry>
        <material>
          <diffuse>${CHILD_VISUAL_RGBA}</diffuse>
        </material>
      </visual>
      <collision name="child_collision_primary">
        <pose>${poseText(LINK_TRUTH.child_link.collisions[0].origin)}</pose>
        <geometry><box><size>0.18 0.14 0.1</size></box></geometry>
      </collision>
      <collision name="child_collision_secondary">
        <pose>${poseText(LINK_TRUTH.child_link.collisions[1].origin)}</pose>
        <geometry><box><size>0.1 0.08 0.06</size></box></geometry>
      </collision>
    </link>
    <joint name="${JOINT_TRUTH.id}" type="revolute">
      <parent>${JOINT_TRUTH.parentLinkId}</parent>
      <child>${JOINT_TRUTH.childLinkId}</child>
      <axis>
        <xyz>${JOINT_TRUTH.axis.x} ${JOINT_TRUTH.axis.y} ${JOINT_TRUTH.axis.z}</xyz>
        <limit><lower>-1</lower><upper>1</upper><effort>10</effort><velocity>2</velocity></limit>
        <dynamics><damping>${JOINT_TRUTH.dynamics.damping}</damping><friction>${JOINT_TRUTH.dynamics.friction}</friction></dynamics>
      </axis>
    </joint>
  </model>
</sdf>`;
}

function createMjcfSource(): string {
  return `<?xml version="1.0"?>
<mujoco model="mujoco_display_probe">
  <compiler angle="radian" />
  <asset>
    <material name="base_paint" rgba="${BASE_VISUAL_RGBA}" />
    <material name="child_paint" rgba="${CHILD_VISUAL_RGBA}" />
  </asset>
  <worldbody>
    <body name="base_link">
      <inertial
        pos="${xyzText(LINK_TRUTH.base_link.inertial.origin)}"
        euler="${rpyText(LINK_TRUTH.base_link.inertial.origin)}"
        mass="${LINK_TRUTH.base_link.inertial.mass}"
        fullinertia="0.21 0.31 0.41 0.01 0.02 0.03" />
      <geom
        name="base_visual"
        type="box"
        size="${mjcfBoxHalfSizeText()}"
        pos="${xyzText(LINK_TRUTH.base_link.visual.origin)}"
        euler="${rpyText(LINK_TRUTH.base_link.visual.origin)}"
        material="base_paint"
        group="1"
        contype="0"
        conaffinity="0" />
      <geom
        name="base_collision"
        type="box"
        size="0.15 0.12 0.08"
        pos="${xyzText(LINK_TRUTH.base_link.collisions[0].origin)}"
        euler="${rpyText(LINK_TRUTH.base_link.collisions[0].origin)}"
        group="3" />
      <body name="child_link" pos="${xyzText(JOINT_TRUTH.origin)}" euler="${rpyText(JOINT_TRUTH.origin)}">
        <joint
          name="${JOINT_TRUTH.id}"
          type="hinge"
          axis="${JOINT_TRUTH.axis.x} ${JOINT_TRUTH.axis.y} ${JOINT_TRUTH.axis.z}"
          range="-1 1"
          actuatorfrcrange="-10 10"
          damping="${JOINT_TRUTH.dynamics.damping}"
          frictionloss="${JOINT_TRUTH.dynamics.friction}" />
        <inertial
          pos="${xyzText(LINK_TRUTH.child_link.inertial.origin)}"
          euler="${rpyText(LINK_TRUTH.child_link.inertial.origin)}"
          mass="${LINK_TRUTH.child_link.inertial.mass}"
          fullinertia="0.11 0.12 0.13 0.004 0.005 0.006" />
        <geom
          name="child_visual"
          type="box"
          size="0.1 0.08 0.06"
          pos="${xyzText(LINK_TRUTH.child_link.visual.origin)}"
          euler="${rpyText(LINK_TRUTH.child_link.visual.origin)}"
          material="child_paint"
          group="1"
          contype="0"
          conaffinity="0" />
        <geom
          name="child_collision_primary"
          type="box"
          size="0.09 0.07 0.05"
          pos="${xyzText(LINK_TRUTH.child_link.collisions[0].origin)}"
          euler="${rpyText(LINK_TRUTH.child_link.collisions[0].origin)}"
          group="3" />
        <geom
          name="child_collision_secondary"
          type="box"
          size="0.05 0.04 0.03"
          pos="${xyzText(LINK_TRUTH.child_link.collisions[1].origin)}"
          euler="${rpyText(LINK_TRUTH.child_link.collisions[1].origin)}"
          group="3" />
      </body>
    </body>
  </worldbody>
</mujoco>`;
}

function createUsdSnapshot(extension: 'usd' | 'usda'): UsdSceneSnapshot {
  const descriptors = [
    descriptor('/Robot/base_link/visuals/base_visual', 'visuals', 'base_visual', 0, 0.4, 0.2, 0.1),
    descriptor(
      '/Robot/base_link/collisions/base_collision',
      'collisions',
      'base_collision',
      0,
      0.3,
      0.24,
      0.16,
    ),
    descriptor(
      '/Robot/child_link/visuals/child_visual',
      'visuals',
      'child_visual',
      0,
      0.2,
      0.16,
      0.12,
    ),
    descriptor(
      '/Robot/child_link/collisions/child_collision_primary',
      'collisions',
      'child_collision_primary',
      0,
      0.18,
      0.14,
      0.1,
    ),
    descriptor(
      '/Robot/child_link/collisions/child_collision_secondary',
      'collisions',
      'child_collision_secondary',
      1,
      0.1,
      0.08,
      0.06,
    ),
  ];

  return {
    stageSourcePath: `/fixtures/display_probe.${extension}`,
    stage: { defaultPrimPath: '/Robot' },
    robotTree: {
      linkParentPairs: [
        ['/Robot/base_link', null],
        ['/Robot/child_link', '/Robot/base_link'],
      ],
      rootLinkPaths: ['/Robot/base_link'],
    },
    robotMetadataSnapshot: {
      stageSourcePath: `/fixtures/display_probe.${extension}`,
      linkParentPairs: [
        ['/Robot/base_link', null],
        ['/Robot/child_link', '/Robot/base_link'],
      ],
      jointCatalogEntries: [
        {
          linkPath: '/Robot/child_link',
          childLinkPath: '/Robot/child_link',
          parentLinkPath: '/Robot/base_link',
          jointPath: '/Robot/joints/base_to_child',
          jointName: JOINT_TRUTH.id,
          jointTypeName: 'revolute',
          axisLocal: [JOINT_TRUTH.axis.x, JOINT_TRUTH.axis.y, JOINT_TRUTH.axis.z],
          originXyz: [JOINT_TRUTH.origin.xyz.x, JOINT_TRUTH.origin.xyz.y, JOINT_TRUTH.origin.xyz.z],
          originQuatWxyz: quaternionWxyzFromPose(JOINT_TRUTH.origin),
          lowerLimitDeg: -57.29577951308232,
          upperLimitDeg: 57.29577951308232,
          driveDamping: JOINT_TRUTH.dynamics.damping,
          driveMaxForce: 10,
        },
      ],
      linkDynamicsEntries: [
        {
          linkPath: '/Robot/base_link',
          mass: LINK_TRUTH.base_link.inertial.mass,
          centerOfMassLocal: vectorArray(LINK_TRUTH.base_link.inertial.origin.xyz),
          principalAxesLocalWxyz: quaternionWxyzFromPose(LINK_TRUTH.base_link.inertial.origin),
          diagonalInertia: [
            LINK_TRUTH.base_link.inertial.inertia.ixx,
            LINK_TRUTH.base_link.inertial.inertia.iyy,
            LINK_TRUTH.base_link.inertial.inertia.izz,
          ],
        },
        {
          linkPath: '/Robot/child_link',
          mass: LINK_TRUTH.child_link.inertial.mass,
          centerOfMassLocal: vectorArray(LINK_TRUTH.child_link.inertial.origin.xyz),
          principalAxesLocalWxyz: quaternionWxyzFromPose(LINK_TRUTH.child_link.inertial.origin),
          diagonalInertia: [
            LINK_TRUTH.child_link.inertial.inertia.ixx,
            LINK_TRUTH.child_link.inertial.inertia.iyy,
            LINK_TRUTH.child_link.inertial.inertia.izz,
          ],
        },
      ],
      meshCountsByLinkPath: {
        '/Robot/base_link': {
          visualMeshCount: 1,
          collisionMeshCount: 1,
          collisionPrimitiveCounts: { cube: 1 },
        },
        '/Robot/child_link': {
          visualMeshCount: 1,
          collisionMeshCount: 2,
          collisionPrimitiveCounts: { cube: 2 },
        },
      },
    },
    render: {
      meshDescriptors: descriptors,
      materials: [
        {
          materialId: '/Looks/base_visual',
          name: 'base_paint',
          color: [0.4, 0.6, 0.8, 1],
          colorSpace: 'srgb',
          roughness: 0.42,
          metalness: 0.08,
        },
        {
          materialId: '/Looks/child_visual',
          name: 'child_paint',
          color: [0.8, 0.4, 0.2, 1],
          colorSpace: 'srgb',
          roughness: 0.5,
          metalness: 0.02,
        },
      ],
    },
  };
}

function descriptor(
  resolvedPrimPath: string,
  sectionName: 'visuals' | 'collisions',
  name: string,
  ordinal: number,
  x: number,
  y: number,
  z: number,
): UsdSceneMeshDescriptor {
  const ownerPath = resolvedPrimPath.replace(
    /\/(?:visuals|collisions)\/[^/]+$/u,
    `/${sectionName}`,
  );
  return {
    meshId: `${ownerPath}.proto_box_id${ordinal}`,
    sectionName,
    resolvedPrimPath,
    primType: 'cube',
    extentSize: [x, y, z],
    materialId: `/Looks/${name}`,
  };
}

function quaternionWxyzFromPose(value: PoseTruth): [number, number, number, number] {
  const quaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(value.rpy.r, value.rpy.p, value.rpy.y, 'ZYX'),
  );
  return [quaternion.w, quaternion.x, quaternion.y, quaternion.z];
}

function vectorArray(value: Vector3): [number, number, number] {
  return [value.x, value.y, value.z];
}

function createRuntimeTransformMap(): Map<string, THREE.Matrix4> {
  const baseWorld = new THREE.Matrix4().identity();
  const childWorld = createOriginMatrix(JOINT_TRUTH.origin);
  const transforms = new Map<string, THREE.Matrix4>([
    ['/Robot/base_link', baseWorld],
    ['/Robot/child_link', childWorld],
  ]);

  const linkWorlds: Array<[string, THREE.Matrix4, LinkTruth]> = [
    ['/Robot/base_link', baseWorld, LINK_TRUTH.base_link],
    ['/Robot/child_link', childWorld, LINK_TRUTH.child_link],
  ];

  linkWorlds.forEach(([linkPath, linkWorld, truth]) => {
    transforms.set(
      `${linkPath}/visuals/${linkPath.endsWith('base_link') ? 'base_visual' : 'child_visual'}`,
      linkWorld.clone().multiply(createOriginMatrix(truth.visual.origin)),
    );
    truth.collisions.forEach((collision, index) => {
      const collisionName = linkPath.endsWith('base_link')
        ? 'base_collision'
        : index === 0
          ? 'child_collision_primary'
          : 'child_collision_secondary';
      transforms.set(
        `${linkPath}/collisions/${collisionName}`,
        linkWorld.clone().multiply(createOriginMatrix(collision.origin)),
      );
    });
  });

  return transforms;
}

function loadSourceRobotData(
  id: TestCaseId,
  fileName: string,
  format: ImportFormat,
  content: string,
): RobotData {
  const file: RobotFile = {
    name: fileName,
    format: format === 'mjcf' ? 'mjcf' : format,
    content,
  };
  const result = resolveRobotFileData(file, {
    availableFiles: [file],
    allFileContents: { [fileName]: content },
    mjcfExternalAssetValidation: 'never',
  });
  if (result.status !== 'ready') {
    const message = result.status === 'error' ? result.message : result.status;
    throw new Error(`${id} import did not produce robot data: ${message ?? 'unknown error'}`);
  }
  return result.robotData;
}

function loadUsdRobotData(extension: 'usd' | 'usda'): RobotData {
  const snapshot = createUsdSnapshot(extension);
  const adapted = adaptUsdViewerSnapshotToRobotData(snapshot, {
    fileName: `display_probe.${extension}`,
  });
  if (!adapted) {
    throw new Error(`${extension} snapshot did not adapt to robot data`);
  }

  const runtimeTransforms = createRuntimeTransformMap();
  const hydrated = hydrateUsdViewerRobotResolutionFromRuntime(adapted, snapshot, {
    getPreferredLinkWorldTransform: (linkPath: string) =>
      runtimeTransforms.get(linkPath)?.clone() ?? null,
    getWorldTransformForPrimPath: (primPath: string) =>
      runtimeTransforms.get(primPath)?.clone() ?? null,
  });
  if (!hydrated) {
    throw new Error(`${extension} snapshot did not hydrate to robot data`);
  }

  return {
    ...hydrated.robotData,
    inspectionContext: { sourceFormat: 'usd' },
  };
}

function createCaseDefinitions(): CaseDefinition[] {
  return [
    {
      id: 'mujoco',
      sourceLabel: 'MJCF/MuJoCo XML',
      loadRobotData: () =>
        loadSourceRobotData('mujoco', 'display_probe.xml', 'mjcf', createMjcfSource()),
    },
    {
      id: 'urdf',
      sourceLabel: 'URDF',
      loadRobotData: () =>
        loadSourceRobotData(
          'urdf',
          'display_probe.urdf',
          'urdf',
          createUrdfSource('urdf_display_probe'),
        ),
    },
    {
      id: 'xacro',
      sourceLabel: 'Xacro-expanded URDF',
      loadRobotData: () =>
        loadSourceRobotData(
          'xacro',
          'display_probe.urdf.xacro',
          'xacro',
          createUrdfSource('xacro_display_probe', true),
        ),
    },
    {
      id: 'sdf',
      sourceLabel: 'SDF',
      loadRobotData: () =>
        loadSourceRobotData('sdf', 'display_probe.sdf', 'sdf', createSdfSource()),
    },
    {
      id: 'usd',
      sourceLabel: 'USD viewer snapshot',
      loadRobotData: () => loadUsdRobotData('usd'),
    },
    {
      id: 'usda',
      sourceLabel: 'USDA viewer snapshot',
      loadRobotData: () => loadUsdRobotData('usda'),
    },
  ];
}

function getCheckRunner(checks: CheckRecord[]) {
  return (name: string, assertion: () => void): void => {
    try {
      assertion();
      checks.push({ name, pass: true });
    } catch (error) {
      checks.push({
        name,
        pass: false,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  };
}

function getExpectedLinks(caseId: TestCaseId): Record<'base_link' | 'child_link', LinkTruth> {
  const expected = structuredClone(LINK_TRUTH) as Record<'base_link' | 'child_link', LinkTruth>;

  if (caseId === 'usd' || caseId === 'usda') {
    expected.base_link.inertial.inertia.ixy = 0;
    expected.base_link.inertial.inertia.ixz = 0;
    expected.base_link.inertial.inertia.iyz = 0;
    expected.child_link.inertial.inertia.ixy = 0;
    expected.child_link.inertial.inertia.ixz = 0;
    expected.child_link.inertial.inertia.iyz = 0;
  }

  return expected;
}

function getExpectedJoint(caseId: TestCaseId): JointTruth {
  const expected = structuredClone(JOINT_TRUTH) as JointTruth;

  if (caseId === 'mujoco') {
    expected.limit.velocity = 0;
  }

  if (caseId === 'usd' || caseId === 'usda') {
    expected.limit.velocity = 10;
    expected.dynamics.friction = 0;
  }

  return expected;
}

function getExpectedSourceFormat(caseId: TestCaseId): string {
  if (caseId === 'mujoco') return 'mjcf';
  if (caseId === 'usda') return 'usd';
  return caseId;
}

function getExpectedMaterialSource(caseId: TestCaseId): UrdfVisual['materialSource'] | undefined {
  if (caseId === 'urdf' || caseId === 'xacro' || caseId === 'usd' || caseId === 'usda') {
    return 'named';
  }
  if (caseId === 'sdf') {
    return 'inline';
  }
  return undefined;
}

function shouldExpectAuthoredMaterialName(caseId: TestCaseId): boolean {
  return caseId === 'mujoco' || caseId === 'urdf' || caseId === 'xacro';
}

function assertFiniteNumber(value: number, label: string): void {
  if (!Number.isFinite(value)) {
    throw new Error(`${label} expected finite number, got ${value}`);
  }
}

function assertClose(actual: number, expected: number, tolerance: number, label: string): void {
  assertFiniteNumber(actual, label);
  if (Math.abs(actual - expected) > tolerance) {
    throw new Error(`${label} expected ${expected}, got ${actual}`);
  }
}

function assertVectorClose(
  actual: Vector3 | THREE.Vector3 | null | undefined,
  expected: Vector3 | THREE.Vector3,
  label: string,
  tolerance = POSITION_TOLERANCE,
): void {
  if (!actual) {
    throw new Error(`${label} missing vector`);
  }
  assertClose(Number(actual.x), Number(expected.x), tolerance, `${label}.x`);
  assertClose(Number(actual.y), Number(expected.y), tolerance, `${label}.y`);
  assertClose(Number(actual.z), Number(expected.z), tolerance, `${label}.z`);
}

function assertPoseClose(actual: PoseTruth | undefined, expected: PoseTruth, label: string): void {
  if (!actual) {
    throw new Error(`${label} missing pose`);
  }
  assertVectorClose(actual.xyz, expected.xyz, `${label}.xyz`);
  assertClose(actual.rpy.r, expected.rpy.r, ROTATION_TOLERANCE, `${label}.rpy.r`);
  assertClose(actual.rpy.p, expected.rpy.p, ROTATION_TOLERANCE, `${label}.rpy.p`);
  assertClose(actual.rpy.y, expected.rpy.y, ROTATION_TOLERANCE, `${label}.rpy.y`);
}

function normalizeColor(value: string | null | undefined): string | undefined {
  const normalized = String(value || '')
    .trim()
    .toLowerCase();
  return normalized || undefined;
}

function assertColorClose(
  actual: string | null | undefined,
  expected: string,
  label: string,
): void {
  const normalizedActual = normalizeColor(actual);
  const normalizedExpected = normalizeColor(expected);
  if (normalizedActual !== normalizedExpected) {
    throw new Error(
      `${label} expected ${normalizedExpected}, got ${normalizedActual ?? 'missing'}`,
    );
  }
}

function assertInertiaClose(
  actual: UrdfInertial | undefined,
  expected: LinkTruth['inertial'],
  label: string,
): void {
  if (!actual) {
    throw new Error(`${label} missing inertial data`);
  }
  assertClose(actual.mass, expected.mass, POSITION_TOLERANCE, `${label}.mass`);
  assertPoseClose(actual.origin, expected.origin, `${label}.origin`);
  assertClose(actual.inertia.ixx, expected.inertia.ixx, POSITION_TOLERANCE, `${label}.ixx`);
  assertClose(actual.inertia.ixy, expected.inertia.ixy, POSITION_TOLERANCE, `${label}.ixy`);
  assertClose(actual.inertia.ixz, expected.inertia.ixz, POSITION_TOLERANCE, `${label}.ixz`);
  assertClose(actual.inertia.iyy, expected.inertia.iyy, POSITION_TOLERANCE, `${label}.iyy`);
  assertClose(actual.inertia.iyz, expected.inertia.iyz, POSITION_TOLERANCE, `${label}.iyz`);
  assertClose(actual.inertia.izz, expected.inertia.izz, POSITION_TOLERANCE, `${label}.izz`);
}

function assertGeometryClose(
  actual: UrdfVisual | undefined,
  expected: GeometryTruth,
  label: string,
): void {
  if (!actual) {
    throw new Error(`${label} missing geometry`);
  }
  if (actual.type !== expected.type) {
    throw new Error(`${label}.type expected ${expected.type}, got ${actual.type}`);
  }
  assertVectorClose(actual.dimensions, expected.dimensions, `${label}.dimensions`);
  assertPoseClose(actual.origin, expected.origin, `${label}.origin`);
  if (actual.visible === false) {
    throw new Error(`${label}.visible expected not false`);
  }
  if (expected.color) {
    assertColorClose(actual.color, expected.color, `${label}.color`);
  }
}

function assertVisualMaterialClose(
  robotData: RobotData,
  linkId: string,
  actual: UrdfVisual | undefined,
  expected: GeometryTruth,
  caseId: TestCaseId,
  label: string,
): void {
  if (!actual) {
    throw new Error(`${label} missing visual`);
  }
  if (!expected.color) {
    return;
  }

  assertColorClose(actual.color, expected.color, `${label}.color`);

  const expectedMaterialSource = getExpectedMaterialSource(caseId);
  if (expectedMaterialSource && actual.materialSource !== expectedMaterialSource) {
    throw new Error(
      `${label}.materialSource expected ${expectedMaterialSource}, got ${actual.materialSource ?? 'missing'}`,
    );
  }

  const materialState = robotData.materials?.[linkId];
  if (!materialState) {
    throw new Error(`${label}.materialState missing`);
  }
  assertColorClose(materialState.color, expected.color, `${label}.materialState.color`);

  if (caseId === 'usd' || caseId === 'usda') {
    const usdMaterial = materialState.usdMaterial;
    if (!usdMaterial) {
      throw new Error(`${label}.materialState.usdMaterial missing`);
    }
    if (expected.materialName && usdMaterial.name !== expected.materialName) {
      throw new Error(
        `${label}.materialState.usdMaterial.name expected ${expected.materialName}, got ${usdMaterial.name ?? 'missing'}`,
      );
    }
    return;
  }

  const authoredMaterial = actual.authoredMaterials?.[0];
  if (!authoredMaterial) {
    throw new Error(`${label}.authoredMaterials[0] missing`);
  }
  assertColorClose(authoredMaterial.color, expected.color, `${label}.authoredMaterials[0].color`);

  if (shouldExpectAuthoredMaterialName(caseId) && expected.materialName) {
    if (authoredMaterial.name !== expected.materialName) {
      throw new Error(
        `${label}.authoredMaterials[0].name expected ${expected.materialName}, got ${authoredMaterial.name ?? 'missing'}`,
      );
    }
  }
}

function assertJointClose(
  actual: UrdfJoint | undefined,
  expected: JointTruth,
  label: string,
): void {
  if (!actual) {
    throw new Error(`${label} missing joint`);
  }
  if (actual.type !== expected.type) {
    throw new Error(`${label}.type expected ${expected.type}, got ${actual.type}`);
  }
  if (actual.parentLinkId !== expected.parentLinkId) {
    throw new Error(
      `${label}.parent expected ${expected.parentLinkId}, got ${actual.parentLinkId}`,
    );
  }
  if (actual.childLinkId !== expected.childLinkId) {
    throw new Error(`${label}.child expected ${expected.childLinkId}, got ${actual.childLinkId}`);
  }
  assertPoseClose(actual.origin, expected.origin, `${label}.origin`);
  assertVectorClose(actual.axis, expected.axis, `${label}.axis`);
  if (!actual.limit) {
    throw new Error(`${label}.limit missing`);
  }
  assertClose(actual.limit.lower, expected.limit.lower, POSITION_TOLERANCE, `${label}.limit.lower`);
  assertClose(actual.limit.upper, expected.limit.upper, POSITION_TOLERANCE, `${label}.limit.upper`);
  assertClose(
    actual.limit.effort,
    expected.limit.effort,
    POSITION_TOLERANCE,
    `${label}.limit.effort`,
  );
  assertClose(
    actual.limit.velocity,
    expected.limit.velocity,
    POSITION_TOLERANCE,
    `${label}.limit.velocity`,
  );
  assertClose(
    actual.dynamics.damping,
    expected.dynamics.damping,
    POSITION_TOLERANCE,
    `${label}.dynamics.damping`,
  );
  assertClose(
    actual.dynamics.friction,
    expected.dynamics.friction,
    POSITION_TOLERANCE,
    `${label}.dynamics.friction`,
  );
}

function matrixFromPose(value: PoseTruth): THREE.Matrix4 {
  return createOriginMatrix(value);
}

function decomposeMatrix(matrix: THREE.Matrix4): {
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
} {
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(position, quaternion, scale);
  return { position, quaternion: quaternion.normalize() };
}

function assertQuaternionClose(
  actual: THREE.Quaternion,
  expected: THREE.Quaternion,
  label: string,
): void {
  const normalizedActual = actual.clone().normalize();
  const normalizedExpected = expected.clone().normalize();
  const dot = Math.abs(normalizedActual.dot(normalizedExpected));
  if (Math.abs(1 - dot) > ROTATION_TOLERANCE) {
    throw new Error(
      `${label} expected quaternion ${normalizedExpected
        .toArray()
        .map((value) => Number(value.toFixed(6)))
        .join(',')}, got ${normalizedActual
        .toArray()
        .map((value) => Number(value.toFixed(6)))
        .join(',')}`,
    );
  }
}

function assertObjectWorldPose(
  object: THREE.Object3D | null | undefined,
  expectedMatrix: THREE.Matrix4,
  label: string,
): void {
  if (!object) {
    throw new Error(`${label} missing runtime object`);
  }
  object.updateWorldMatrix(true, true);
  const expected = decomposeMatrix(expectedMatrix);
  const actual = decomposeMatrix(object.matrixWorld);
  assertVectorClose(actual.position, expected.position, `${label}.position`);
  assertQuaternionClose(actual.quaternion, expected.quaternion, `${label}.quaternion`);
}

function getRuntimeLink(robot: THREE.Object3D, linkId: string): THREE.Object3D | null {
  const links = (robot as THREE.Object3D & { links?: Record<string, THREE.Object3D> }).links;
  return links?.[linkId] ?? null;
}

function getRuntimeJoint(robot: THREE.Object3D, jointId: string): THREE.Object3D | null {
  const joints = (robot as THREE.Object3D & { joints?: Record<string, THREE.Object3D> }).joints;
  return joints?.[jointId] ?? null;
}

function getRuntimeGeometry(
  robot: THREE.Object3D,
  linkId: string,
  role: 'visual' | 'collision',
  index: number,
): THREE.Object3D | null {
  const link = getRuntimeLink(robot, linkId);
  if (!link) {
    return null;
  }
  const runtimeKey = `${linkId}::${role}::${index}`;
  return (
    link.children.find(
      (child) => child.name === runtimeKey || child.userData?.runtimeKey === runtimeKey,
    ) ?? null
  );
}

function countRuntimeGeometryByRole(robot: THREE.Object3D, role: 'visual' | 'collision'): number {
  let count = 0;
  robot.traverse((child) => {
    if (child.userData?.geometryRole === role) {
      count += 1;
    }
  });
  return count;
}

function findFirstMesh(object: THREE.Object3D | null | undefined): THREE.Mesh | null {
  if (!object) {
    return null;
  }
  let result: THREE.Mesh | null = null;
  object.traverse((child) => {
    if (!result && (child as THREE.Mesh).isMesh) {
      result = child as THREE.Mesh;
    }
  });
  return result;
}

function getMaterialColorHex(
  material: THREE.Material | THREE.Material[] | undefined,
): string | null {
  const firstMaterial = Array.isArray(material) ? material[0] : material;
  const color = (firstMaterial as (THREE.Material & { color?: THREE.Color }) | undefined)?.color;
  return color ? `#${color.getHexString().toLowerCase()}` : null;
}

function assertRuntimeGeometryDimensions(
  object: THREE.Object3D | null | undefined,
  expected: GeometryTruth,
  label: string,
): void {
  if (!object) {
    throw new Error(`${label} missing runtime object`);
  }
  assertVectorClose(
    object.userData.geometryDimensions,
    expected.dimensions,
    `${label}.userData.dimensions`,
  );

  if (expected.type !== GeometryType.BOX) {
    return;
  }

  const mesh = findFirstMesh(object);
  if (!mesh) {
    throw new Error(`${label}.mesh missing`);
  }
  assertVectorClose(mesh.scale, expected.dimensions, `${label}.mesh.scale`);
}

function assertRuntimeVisualMaterialColor(
  object: THREE.Object3D | null | undefined,
  expected: GeometryTruth,
  label: string,
): void {
  if (!expected.color) {
    return;
  }
  const mesh = findFirstMesh(object);
  if (!mesh) {
    throw new Error(`${label}.mesh missing`);
  }
  assertColorClose(getMaterialColorHex(mesh.material), expected.color, `${label}.material.color`);
}

function validateSemanticRobotData(
  robotData: RobotData,
  expectedLinks: Record<'base_link' | 'child_link', LinkTruth>,
  expectedJoint: JointTruth,
  caseId: TestCaseId,
  check: ReturnType<typeof getCheckRunner>,
): void {
  check('semantic source format', () => {
    const expectedSourceFormat = getExpectedSourceFormat(caseId);
    const actualSourceFormat = robotData.inspectionContext?.sourceFormat;
    if (actualSourceFormat !== expectedSourceFormat) {
      throw new Error(`expected ${expectedSourceFormat}, got ${actualSourceFormat ?? 'missing'}`);
    }
  });

  check('semantic root link is base_link', () => {
    if (robotData.rootLinkId !== 'base_link') {
      throw new Error(`expected base_link root, got ${robotData.rootLinkId}`);
    }
  });

  check('semantic topology counts', () => {
    const linkCount = Object.keys(robotData.links).length;
    const jointCount = Object.keys(robotData.joints).length;
    const visualCount = Object.values(robotData.links).reduce(
      (sum, link) => sum + getVisualGeometryEntries(link).length,
      0,
    );
    const collisionCount = Object.values(robotData.links).reduce(
      (sum, link) => sum + getCollisionGeometryEntries(link).length,
      0,
    );
    if (linkCount !== 2 || jointCount !== 1 || visualCount !== 2 || collisionCount !== 3) {
      throw new Error(
        `expected links=2 joints=1 visuals=2 collisions=3, got links=${linkCount} joints=${jointCount} visuals=${visualCount} collisions=${collisionCount}`,
      );
    }
  });

  check('semantic total mass', () => {
    const actualTotalMass = Object.values(robotData.links).reduce(
      (sum, link) => sum + (link.inertial?.mass ?? 0),
      0,
    );
    const expectedTotalMass = Object.values(expectedLinks).reduce(
      (sum, link) => sum + link.inertial.mass,
      0,
    );
    assertClose(actualTotalMass, expectedTotalMass, POSITION_TOLERANCE, 'totalMass');
  });

  Object.entries(expectedLinks).forEach(([linkId, expected]) => {
    const link = robotData.links[linkId];
    check(`semantic ${linkId} exists`, () => {
      if (!link) {
        throw new Error(`missing link ${linkId}`);
      }
    });
    if (!link) return;

    check(`semantic ${linkId} inertial mass/COM/inertia`, () =>
      assertInertiaClose(link.inertial, expected.inertial, `${linkId}.inertial`),
    );

    check(`semantic ${linkId} visual origin`, () => {
      const visual = getVisualGeometryEntries(link)[0]?.geometry;
      assertGeometryClose(visual, expected.visual, `${linkId}.visual[0]`);
    });

    check(`semantic ${linkId} visual material`, () => {
      const visual = getVisualGeometryEntries(link)[0]?.geometry;
      assertVisualMaterialClose(
        robotData,
        linkId,
        visual,
        expected.visual,
        caseId,
        `${linkId}.visual[0]`,
      );
    });

    check(`semantic ${linkId} collision count`, () => {
      const collisions = getCollisionGeometryEntries(link);
      if (collisions.length !== expected.collisions.length) {
        throw new Error(`expected ${expected.collisions.length}, got ${collisions.length}`);
      }
    });

    expected.collisions.forEach((collision, index) => {
      check(`semantic ${linkId} collision[${index}] origin`, () => {
        const actual = getCollisionGeometryEntries(link)[index]?.geometry;
        assertGeometryClose(actual, collision, `${linkId}.collision[${index}]`);
      });
    });
  });

  check('semantic joint origin and axis', () =>
    assertJointClose(robotData.joints[expectedJoint.id], expectedJoint, expectedJoint.id),
  );
}

async function buildRuntimeRobot(robotData: RobotData): Promise<THREE.Object3D> {
  return buildRuntimeRobotFromState({
    robotName: robotData.name,
    links: robotData.links,
    joints: robotData.joints,
    materials: robotData.materials,
    inspectionContext: robotData.inspectionContext,
    rootLinkId: robotData.rootLinkId,
    manager: new THREE.LoadingManager(),
    loadMeshCb: (_meshPath, _manager, done) => done(null),
    yieldIfNeeded: async () => {},
  });
}

function validateRuntimeDisplay(
  robotData: RobotData,
  robot: THREE.Object3D,
  expectedLinks: Record<'base_link' | 'child_link', LinkTruth>,
  expectedJoint: JointTruth,
  check: ReturnType<typeof getCheckRunner>,
): void {
  const sceneNodes = getRobotSceneNodeIndex(robot);
  syncOriginAxesVisualizationForLinks({
    links: sceneNodes.links,
    showOrigins: true,
    showOriginsOverlay: true,
    originSize: 0.25,
  });
  syncJointAxesVisualizationForJoints({
    joints: sceneNodes.joints,
    showJointAxes: true,
    showJointAxesOverlay: true,
    jointAxisSize: 0.5,
  });
  syncInertiaVisualizationForLinks({
    links: sceneNodes.links,
    robotLinks: robotData.links,
    showInertia: true,
    showInertiaOverlay: true,
    showCenterOfMass: true,
    showCoMOverlay: true,
    centerOfMassSize: 0.02,
  });
  robot.updateMatrixWorld(true);

  const linkWorldMatrices = computeLinkWorldMatrices(robotData);

  check('display topology and helper counts', () => {
    const originHelperCount = sceneNodes.links.filter((link) => link.userData.__originAxes).length;
    const comHelperCount = sceneNodes.links.filter((link) => link.userData.__comVisual).length;
    const inertiaHelperCount = sceneNodes.links.filter(
      (link) => link.userData.__inertiaVisualGroup,
    ).length;
    const jointAxisHelperCount = sceneNodes.joints.filter(
      (joint) => joint.userData.__jointAxisViz,
    ).length;
    const visualCount = countRuntimeGeometryByRole(robot, 'visual');
    const collisionCount = countRuntimeGeometryByRole(robot, 'collision');

    if (
      sceneNodes.links.length !== 2 ||
      sceneNodes.joints.length !== 1 ||
      visualCount !== 2 ||
      collisionCount !== 3 ||
      originHelperCount !== 2 ||
      comHelperCount !== 2 ||
      inertiaHelperCount !== 2 ||
      jointAxisHelperCount !== 1
    ) {
      throw new Error(
        `expected links=2 joints=1 visuals=2 collisions=3 originHelpers=2 comHelpers=2 inertiaHelpers=2 jointAxisHelpers=1, got links=${sceneNodes.links.length} joints=${sceneNodes.joints.length} visuals=${visualCount} collisions=${collisionCount} originHelpers=${originHelperCount} comHelpers=${comHelperCount} inertiaHelpers=${inertiaHelperCount} jointAxisHelpers=${jointAxisHelperCount}`,
      );
    }
  });

  Object.entries(expectedLinks).forEach(([linkId, expected]) => {
    const link = getRuntimeLink(robot, linkId);
    const linkWorld = linkWorldMatrices[linkId];

    check(`display ${linkId} runtime link pose`, () => {
      if (!linkWorld) {
        throw new Error(`missing expected world matrix for ${linkId}`);
      }
      assertObjectWorldPose(link, linkWorld, `${linkId}.runtimeLink`);
    });

    check(`display ${linkId} origin axes pose`, () => {
      if (!linkWorld) {
        throw new Error(`missing expected world matrix for ${linkId}`);
      }
      const originAxes = link?.userData.__originAxes as THREE.Object3D | undefined;
      assertObjectWorldPose(originAxes, linkWorld, `${linkId}.originAxes`);
    });

    check(`display ${linkId} center of mass helper pose`, () => {
      if (!linkWorld) {
        throw new Error(`missing expected world matrix for ${linkId}`);
      }
      const comVisual = link?.userData.__comVisual as THREE.Object3D | undefined;
      assertObjectWorldPose(
        comVisual,
        linkWorld.clone().multiply(matrixFromPose(expected.inertial.origin)),
        `${linkId}.centerOfMass`,
      );
    });

    check(`display ${linkId} inertia helper pose`, () => {
      if (!linkWorld) {
        throw new Error(`missing expected world matrix for ${linkId}`);
      }
      const inertiaGroup = link?.userData.__inertiaVisualGroup as THREE.Object3D | undefined;
      assertObjectWorldPose(
        inertiaGroup,
        linkWorld.clone().multiply(matrixFromPose(expected.inertial.origin)),
        `${linkId}.inertiaGroup`,
      );
    });

    check(`display ${linkId} visual[0] pose`, () => {
      if (!linkWorld) {
        throw new Error(`missing expected world matrix for ${linkId}`);
      }
      const visualObject = getRuntimeGeometry(robot, linkId, 'visual', 0);
      assertObjectWorldPose(
        visualObject,
        linkWorld.clone().multiply(matrixFromPose(expected.visual.origin)),
        `${linkId}.visual[0]`,
      );
      assertRuntimeGeometryDimensions(visualObject, expected.visual, `${linkId}.visual[0]`);
      assertRuntimeVisualMaterialColor(visualObject, expected.visual, `${linkId}.visual[0]`);
    });

    expected.collisions.forEach((collision, index) => {
      check(`display ${linkId} collision[${index}] pose`, () => {
        if (!linkWorld) {
          throw new Error(`missing expected world matrix for ${linkId}`);
        }
        const collisionObject = getRuntimeGeometry(robot, linkId, 'collision', index);
        assertObjectWorldPose(
          collisionObject,
          linkWorld.clone().multiply(matrixFromPose(collision.origin)),
          `${linkId}.collision[${index}]`,
        );
        assertRuntimeGeometryDimensions(
          collisionObject,
          collision,
          `${linkId}.collision[${index}]`,
        );
      });
    });
  });

  check('display joint axis helper pose and direction', () => {
    const jointObject = getRuntimeJoint(robot, expectedJoint.id);
    const parentWorld = linkWorldMatrices[expectedJoint.parentLinkId];
    if (!parentWorld) {
      throw new Error(`missing expected parent matrix for ${expectedJoint.parentLinkId}`);
    }
    const jointWorld = parentWorld.clone().multiply(matrixFromPose(expectedJoint.origin));
    assertObjectWorldPose(jointObject, jointWorld, `${expectedJoint.id}.runtimeJoint`);

    const jointAxisHelper = jointObject?.userData.__jointAxisViz as THREE.Object3D | undefined;
    if (!jointAxisHelper) {
      throw new Error(`${expectedJoint.id}.jointAxisHelper missing`);
    }
    jointAxisHelper.updateWorldMatrix(true, true);
    const actualDirection = new THREE.Vector3(0, 0, 1)
      .applyQuaternion(jointAxisHelper.getWorldQuaternion(new THREE.Quaternion()))
      .normalize();
    const expectedDirection = new THREE.Vector3(
      expectedJoint.axis.x,
      expectedJoint.axis.y,
      expectedJoint.axis.z,
    )
      .applyQuaternion(decomposeMatrix(jointWorld).quaternion)
      .normalize();
    assertVectorClose(
      actualDirection,
      expectedDirection,
      `${expectedJoint.id}.jointAxisDirection`,
      ROTATION_TOLERANCE,
    );
  });
}

async function validateCase(definition: CaseDefinition): Promise<CaseReport> {
  const checks: CheckRecord[] = [];
  const check = getCheckRunner(checks);

  try {
    const robotData = definition.loadRobotData();
    const expectedLinks = getExpectedLinks(definition.id);
    const expectedJoint = getExpectedJoint(definition.id);
    validateSemanticRobotData(robotData, expectedLinks, expectedJoint, definition.id, check);
    const runtimeRobot = await buildRuntimeRobot(robotData);
    validateRuntimeDisplay(robotData, runtimeRobot, expectedLinks, expectedJoint, check);
  } catch (error) {
    checks.push({
      name: 'case setup',
      pass: false,
      message: error instanceof Error ? (error.stack ?? error.message) : String(error),
    });
  }

  const failCount = checks.filter((entry) => !entry.pass).length;
  return {
    id: definition.id,
    sourceLabel: definition.sourceLabel,
    pass: failCount === 0,
    checkCount: checks.length,
    failCount,
    checks,
  };
}

function parseCliArgs(argv: string[]): { outputPath: string; cases: TestCaseId[] } {
  const options = {
    outputPath: DEFAULT_OUTPUT_PATH,
    cases: [] as TestCaseId[],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (!value) {
        throw new Error(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--format':
      case '--case': {
        const normalized = normalizeCaseId(nextValue());
        if (!normalized) {
          throw new Error(
            `Unknown format/case. Supported: mujoco, mjcf, urdf, xacro, sdf, usd, usda`,
          );
        }
        if (!options.cases.includes(normalized)) {
          options.cases.push(normalized);
        }
        break;
      }
      case '--help':
      case '-h':
        process.stdout.write(
          [
            'Usage: npx tsx -r tsconfig-paths/register scripts/test/truth/validate_physics_display_transforms.ts [options]',
            '',
            'Options:',
            `  --output <path>   JSON report path. Default: ${DEFAULT_OUTPUT_PATH}`,
            '  --format <name>   Case filter. Repeatable. Supported: mujoco, mjcf, urdf, xacro, sdf, usd, usda',
            '  --help            Show this help.',
            '',
          ].join('\n'),
        );
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return {
    outputPath: options.outputPath,
    cases:
      options.cases.length > 0 ? options.cases : ['mujoco', 'urdf', 'xacro', 'sdf', 'usd', 'usda'],
  };
}

function normalizeCaseId(value: string): TestCaseId | null {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'mjcf') return 'mujoco';
  if (
    normalized === 'mujoco' ||
    normalized === 'urdf' ||
    normalized === 'xacro' ||
    normalized === 'sdf' ||
    normalized === 'usd' ||
    normalized === 'usda'
  ) {
    return normalized;
  }
  return null;
}

async function writeReport(outputPath: string, cases: CaseReport[]): Promise<ValidationReport> {
  const report: ValidationReport = {
    generatedAt: new Date().toISOString(),
    caseCount: cases.length,
    passCount: cases.filter((entry) => entry.pass).length,
    failCount: cases.filter((entry) => !entry.pass).length,
    checkCount: cases.reduce((sum, entry) => sum + entry.checkCount, 0),
    cases,
  };
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  return report;
}

async function main(): Promise<void> {
  installDomGlobals();
  const options = parseCliArgs(process.argv.slice(2));
  const definitions = createCaseDefinitions().filter((definition) =>
    options.cases.includes(definition.id),
  );
  const cases = [] as CaseReport[];

  for (const definition of definitions) {
    cases.push(await validateCase(definition));
  }

  const report = await writeReport(options.outputPath, cases);
  console.log(
    JSON.stringify(
      {
        outputPath: options.outputPath,
        caseCount: report.caseCount,
        passCount: report.passCount,
        failCount: report.failCount,
        checkCount: report.checkCount,
      },
      null,
      2,
    ),
  );

  if (report.failCount > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? (error.stack ?? error.message) : error);
  process.exitCode = 1;
});
