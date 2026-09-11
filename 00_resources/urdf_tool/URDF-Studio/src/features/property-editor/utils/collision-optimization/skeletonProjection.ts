import * as THREE from 'three';

import { mergeAssembly } from '@/core/robot';
import type { AssemblyState, RobotData, UrdfJoint, UrdfVisual } from '@/types';

export type CollisionOptimizationSkeletonProjectionPlane = 'xz' | 'xy' | 'yz';
export type CollisionOptimizationSkeletonProjectionViewMode = 'auto' | 'front';

export type CollisionOptimizationSkeletonProjectionSource =
  | { kind: 'robot'; robot: RobotData }
  | { kind: 'assembly'; assembly: AssemblyState };

export interface CollisionOptimizationSkeletonProjectionNode {
  linkId: string;
  clusterId: string;
  world: {
    x: number;
    y: number;
    z: number;
  };
  projected: {
    x: number;
    y: number;
  };
}

export interface CollisionOptimizationSkeletonProjectionEdge {
  id: string;
  fromLinkId: string;
  toLinkId: string;
  clusterId: string;
}

export interface CollisionOptimizationSkeletonProjection {
  plane: CollisionOptimizationSkeletonProjectionPlane;
  nodes: Record<string, CollisionOptimizationSkeletonProjectionNode>;
  edges: CollisionOptimizationSkeletonProjectionEdge[];
}

export interface CollisionOptimizationSkeletonProjectionOptions {
  viewMode?: CollisionOptimizationSkeletonProjectionViewMode;
}

const UNIT_SCALE = new THREE.Vector3(1, 1, 1);

function createOriginMatrix(origin?: UrdfVisual['origin']): THREE.Matrix4 {
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3(origin?.xyz?.x ?? 0, origin?.xyz?.y ?? 0, origin?.xyz?.z ?? 0);
  const quaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(origin?.rpy?.r ?? 0, origin?.rpy?.p ?? 0, origin?.rpy?.y ?? 0, 'ZYX'),
  );
  matrix.compose(position, quaternion, UNIT_SCALE);
  return matrix;
}

function createJointMotionMatrix(joint: UrdfJoint): THREE.Matrix4 {
  const matrix = new THREE.Matrix4().identity();
  const angle = Number.isFinite(joint.angle) ? joint.angle! : 0;

  if (joint.type === 'revolute' || joint.type === 'continuous') {
    const axis = joint.axis ?? { x: 0, y: 0, z: 1 };
    const axisVector = new THREE.Vector3(axis.x, axis.y, axis.z);
    if (axisVector.lengthSq() > 1e-12 && Math.abs(angle) > 1e-12) {
      axisVector.normalize();
      matrix.makeRotationAxis(axisVector, angle);
    }
    return matrix;
  }

  if (joint.type === 'prismatic') {
    const axis = joint.axis ?? { x: 0, y: 0, z: 1 };
    const axisVector = new THREE.Vector3(axis.x, axis.y, axis.z);
    if (axisVector.lengthSq() > 1e-12 && Math.abs(angle) > 1e-12) {
      axisVector.normalize().multiplyScalar(angle);
      matrix.makeTranslation(axisVector.x, axisVector.y, axisVector.z);
    }
  }

  return matrix;
}

export function computeLinkWorldMatrices(robot: RobotData): Record<string, THREE.Matrix4> {
  const linkMatrices: Record<string, THREE.Matrix4> = {};
  const jointsByParent = new Map<string, UrdfJoint[]>();
  const childLinkIds = new Set<string>();

  Object.values(robot.joints).forEach((joint) => {
    const siblings = jointsByParent.get(joint.parentLinkId) ?? [];
    siblings.push(joint);
    jointsByParent.set(joint.parentLinkId, siblings);
    childLinkIds.add(joint.childLinkId);
  });

  const visit = (linkId: string, parentMatrix: THREE.Matrix4) => {
    if (linkMatrices[linkId]) {
      return;
    }

    linkMatrices[linkId] = parentMatrix.clone();
    const childJoints = jointsByParent.get(linkId) ?? [];

    childJoints.forEach((joint) => {
      const childMatrix = parentMatrix
        .clone()
        .multiply(createOriginMatrix(joint.origin))
        .multiply(createJointMotionMatrix(joint));
      visit(joint.childLinkId, childMatrix);
    });
  };

  const rootCandidates = [
    robot.rootLinkId,
    ...Object.keys(robot.links).filter((linkId) => !childLinkIds.has(linkId)),
    ...Object.keys(robot.links),
  ].filter(
    (linkId, index, values): linkId is string =>
      Boolean(linkId) && values.indexOf(linkId) === index,
  );

  rootCandidates.forEach((rootLinkId) => {
    visit(rootLinkId, new THREE.Matrix4().identity());
  });

  return linkMatrices;
}

function chooseSkeletonProjectionPlane(
  positions: THREE.Vector3[],
): CollisionOptimizationSkeletonProjectionPlane {
  if (positions.length === 0) {
    return 'xz';
  }

  const min = new THREE.Vector3(Infinity, Infinity, Infinity);
  const max = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
  positions.forEach((position) => {
    min.min(position);
    max.max(position);
  });

  const spanX = Math.max(max.x - min.x, 1e-6);
  const spanY = Math.max(max.y - min.y, 1e-6);
  const spanZ = Math.max(max.z - min.z, 1e-6);
  const candidates: Array<{ plane: CollisionOptimizationSkeletonProjectionPlane; area: number }> = [
    { plane: 'xz', area: spanX * spanZ },
    { plane: 'xy', area: spanX * spanY },
    { plane: 'yz', area: spanY * spanZ },
  ];

  candidates.sort((left, right) => right.area - left.area);
  return candidates[0]?.plane ?? 'xz';
}

function chooseFrontSkeletonProjectionPlane(
  positions: THREE.Vector3[],
): CollisionOptimizationSkeletonProjectionPlane {
  if (positions.length === 0) {
    return 'yz';
  }

  const min = new THREE.Vector3(Infinity, Infinity, Infinity);
  const max = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
  positions.forEach((position) => {
    min.min(position);
    max.max(position);
  });

  const spanX = Math.max(max.x - min.x, 1e-6);
  const spanY = Math.max(max.y - min.y, 1e-6);
  const hasReadableLateralSpread = spanY >= Math.max(spanX * 0.15, 1e-3);

  return hasReadableLateralSpread ? 'yz' : 'xz';
}

function projectSkeletonPosition(
  plane: CollisionOptimizationSkeletonProjectionPlane,
  position: THREE.Vector3,
): { x: number; y: number } {
  switch (plane) {
    case 'xy':
      return { x: position.x, y: -position.y };
    case 'yz':
      return { x: position.y, y: -position.z };
    case 'xz':
    default:
      return { x: position.x, y: -position.z };
  }
}

function buildSkeletonClusterIds(robot: RobotData): Record<string, string> {
  const adjacency = new Map<string, string[]>();
  Object.keys(robot.links).forEach((linkId) => {
    adjacency.set(linkId, []);
  });

  Object.values(robot.joints).forEach((joint) => {
    adjacency.get(joint.parentLinkId)?.push(joint.childLinkId);
    adjacency.get(joint.childLinkId)?.push(joint.parentLinkId);
  });

  const clusterIds: Record<string, string> = {};
  const visited = new Set<string>();
  let clusterIndex = 0;

  Object.keys(robot.links)
    .sort((left, right) => left.localeCompare(right))
    .forEach((linkId) => {
      if (visited.has(linkId)) {
        return;
      }

      const clusterId = `cluster-${clusterIndex}`;
      clusterIndex += 1;
      const queue = [linkId];
      visited.add(linkId);

      while (queue.length > 0) {
        const current = queue.shift()!;
        clusterIds[current] = clusterId;

        (adjacency.get(current) ?? []).forEach((neighbor) => {
          if (visited.has(neighbor)) {
            return;
          }

          visited.add(neighbor);
          queue.push(neighbor);
        });
      }
    });

  return clusterIds;
}

export function buildCollisionOptimizationSkeletonProjection(
  source: CollisionOptimizationSkeletonProjectionSource,
  options: CollisionOptimizationSkeletonProjectionOptions = {},
): CollisionOptimizationSkeletonProjection {
  const robot = source.kind === 'robot' ? source.robot : mergeAssembly(source.assembly);
  const linkWorldMatrices = computeLinkWorldMatrices(robot);
  const linkPositions = Object.entries(linkWorldMatrices).map(([linkId, matrix]) => {
    const position = new THREE.Vector3();
    position.setFromMatrixPosition(matrix);
    return { linkId, position };
  });
  const positions = linkPositions.map(({ position }) => position);
  const plane =
    options.viewMode === 'front'
      ? chooseFrontSkeletonProjectionPlane(positions)
      : chooseSkeletonProjectionPlane(positions);
  const clusterIds = buildSkeletonClusterIds(robot);

  return {
    plane,
    nodes: Object.fromEntries(
      linkPositions.map(({ linkId, position }) => [
        linkId,
        {
          linkId,
          clusterId: clusterIds[linkId] ?? 'cluster-0',
          world: {
            x: position.x,
            y: position.y,
            z: position.z,
          },
          projected: projectSkeletonPosition(plane, position),
        },
      ]),
    ),
    edges: Object.values(robot.joints).map((joint, index) => ({
      id: `skeleton-edge::${index}::${joint.parentLinkId}::${joint.childLinkId}`,
      fromLinkId: joint.parentLinkId,
      toLinkId: joint.childLinkId,
      clusterId:
        clusterIds[joint.parentLinkId] ?? clusterIds[joint.childLinkId] ?? `cluster-${index}`,
    })),
  };
}
