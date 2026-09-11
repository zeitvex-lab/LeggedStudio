import * as THREE from 'three';

import { mergeAssembly } from '@/core/robot';
import { GeometryType } from '@/types';
import type { RobotData, UrdfVisual } from '@/types';
import {
  convertGeometryType,
  type MeshAnalysis,
  type MeshClearanceObstacle,
} from '../geometryConversion';
import { computeLinkWorldMatrices } from './skeletonProjection';
import {
  cloneCollisionGeometry,
  getCollisionTargetLinkGroupKey,
  normalizeCollisionGeometry,
  type CollisionOptimizationSource,
  type CollisionTargetRef,
} from './collisionTargets';
import {
  transformGeometryToTargetLinkFrame,
  transformMeshObstaclePointsToTargetLinkFrame,
} from './geometryTransforms';

export interface CollisionOptimizationClearanceWorld {
  robot: RobotData;
  linkWorldMatrices: Record<string, THREE.Matrix4>;
  broadPhaseByTargetId: Record<string, { center: THREE.Vector3; radius: number }>;
}

export interface CollisionClearanceContext {
  siblingGeometries?: UrdfVisual[];
  meshClearanceObstacles?: MeshClearanceObstacle[];
}

export function computeBroadPhaseRadius(
  geometry: UrdfVisual,
  meshAnalysis?: MeshAnalysis | null,
): number | null {
  const dims = geometry.dimensions;

  switch (geometry.type) {
    case GeometryType.SPHERE:
      return Math.max(dims.x, 0);
    case GeometryType.BOX:
      return Math.hypot(dims.x, dims.y, dims.z) / 2;
    case GeometryType.CYLINDER:
      return Math.hypot(Math.max(dims.x, 0), Math.max(dims.y, 0) / 2);
    case GeometryType.CAPSULE:
      return Math.max(Math.max(dims.y, 0) / 2, Math.max(dims.x, 0));
    case GeometryType.MESH:
      if (!meshAnalysis) return null;
      return Math.hypot(meshAnalysis.bounds.x, meshAnalysis.bounds.y, meshAnalysis.bounds.z) / 2;
    default:
      return null;
  }
}

export function computeBroadPhaseCenter(
  geometry: UrdfVisual,
  meshAnalysis?: MeshAnalysis | null,
): { x: number; y: number; z: number } {
  const origin = geometry.origin?.xyz ?? { x: 0, y: 0, z: 0 };

  if (geometry.type === GeometryType.MESH && meshAnalysis?.bounds) {
    return {
      x: origin.x + meshAnalysis.bounds.cx,
      y: origin.y + meshAnalysis.bounds.cy,
      z: origin.z + meshAnalysis.bounds.cz,
    };
  }

  return {
    x: origin.x,
    y: origin.y,
    z: origin.z,
  };
}

function buildSiblingGeometries(
  targets: CollisionTargetRef[],
  target: CollisionTargetRef,
  meshAnalysisByTargetId: Record<string, MeshAnalysis | null>,
): UrdfVisual[] {
  const groupKey = getCollisionTargetLinkGroupKey(target);
  return targets
    .filter(
      (candidate) =>
        candidate.id !== target.id && getCollisionTargetLinkGroupKey(candidate) === groupKey,
    )
    .map((candidate) => {
      if (candidate.geometry.type !== GeometryType.MESH) {
        return cloneCollisionGeometry(candidate.geometry);
      }

      const analysis = meshAnalysisByTargetId[candidate.id];
      if (!analysis) {
        return cloneCollisionGeometry(candidate.geometry);
      }

      const converted = convertGeometryType(candidate.geometry, GeometryType.BOX, analysis);
      return {
        ...normalizeCollisionGeometry(candidate.geometry),
        type: GeometryType.BOX,
        dimensions: { ...converted.dimensions },
        origin: {
          xyz: { ...converted.origin.xyz },
          rpy: { ...converted.origin.rpy },
        },
        meshPath: undefined,
      };
    });
}

function computeWorldBroadPhaseSphere(
  geometry: UrdfVisual,
  meshAnalysis: MeshAnalysis | null | undefined,
  sourceLinkMatrix: THREE.Matrix4 | undefined,
): { center: THREE.Vector3; radius: number } | null {
  if (!sourceLinkMatrix) {
    return null;
  }

  const radius = computeBroadPhaseRadius(geometry, meshAnalysis);
  if (!radius || radius <= 1e-8) {
    return null;
  }

  const localCenter = computeBroadPhaseCenter(geometry, meshAnalysis);
  const worldCenter = new THREE.Vector3(localCenter.x, localCenter.y, localCenter.z).applyMatrix4(
    sourceLinkMatrix,
  );

  return {
    center: worldCenter,
    radius,
  };
}

export function buildCollisionOptimizationClearanceWorld(
  source: CollisionOptimizationSource,
  targets: CollisionTargetRef[],
  meshAnalysisByTargetId: Record<string, MeshAnalysis | null>,
): CollisionOptimizationClearanceWorld | null {
  const robot = source.kind === 'robot' ? source.robot : mergeAssembly(source.assembly);
  if (!robot.rootLinkId || Object.keys(robot.links).length === 0) {
    return null;
  }

  const linkWorldMatrices = computeLinkWorldMatrices(robot);
  if (Object.keys(linkWorldMatrices).length === 0) {
    return null;
  }

  const broadPhaseByTargetId: Record<string, { center: THREE.Vector3; radius: number }> = {};
  targets.forEach((target) => {
    const sphere = computeWorldBroadPhaseSphere(
      target.geometry,
      meshAnalysisByTargetId[target.id],
      linkWorldMatrices[target.linkId],
    );
    if (sphere) {
      broadPhaseByTargetId[target.id] = sphere;
    }
  });

  return {
    robot,
    linkWorldMatrices,
    broadPhaseByTargetId,
  };
}

export function buildNearbyCollisionClearanceContext(
  targets: CollisionTargetRef[],
  target: CollisionTargetRef,
  meshAnalysisByTargetId: Record<string, MeshAnalysis | null>,
  clearanceWorld: CollisionOptimizationClearanceWorld | null,
  includeMeshClearanceObstacles = true,
): CollisionClearanceContext {
  if (!clearanceWorld) {
    const siblingGeometries = buildSiblingGeometries(targets, target, meshAnalysisByTargetId);
    return {
      siblingGeometries: siblingGeometries.length > 0 ? siblingGeometries : undefined,
    };
  }

  const currentLinkMatrix = clearanceWorld.linkWorldMatrices[target.linkId];
  if (!currentLinkMatrix) {
    const siblingGeometries = buildSiblingGeometries(targets, target, meshAnalysisByTargetId);
    return {
      siblingGeometries: siblingGeometries.length > 0 ? siblingGeometries : undefined,
    };
  }

  const currentLinkInverseMatrix = currentLinkMatrix.clone().invert();
  const targetSphere = clearanceWorld.broadPhaseByTargetId[target.id] ?? null;
  const siblingGeometries: UrdfVisual[] = [];
  const meshClearanceObstacles: MeshClearanceObstacle[] = [];

  targets.forEach((candidate) => {
    if (candidate.id === target.id) {
      return;
    }

    const sourceLinkMatrix = clearanceWorld.linkWorldMatrices[candidate.linkId];
    if (!sourceLinkMatrix) {
      return;
    }

    const obstacleSphere = clearanceWorld.broadPhaseByTargetId[candidate.id] ?? null;
    if (targetSphere && obstacleSphere) {
      const maxInfluenceDistance = targetSphere.radius + obstacleSphere.radius + 0.05;
      if (targetSphere.center.distanceTo(obstacleSphere.center) > maxInfluenceDistance) {
        return;
      }
    }

    const geometry = candidate.geometry;
    const analysis = meshAnalysisByTargetId[candidate.id];
    const meshObstacle =
      includeMeshClearanceObstacles &&
      analysis?.surfacePoints?.length &&
      geometry.type === GeometryType.MESH
        ? transformMeshObstaclePointsToTargetLinkFrame(
            analysis.surfacePoints,
            sourceLinkMatrix,
            geometry.origin,
            currentLinkInverseMatrix,
          )
        : null;

    if (meshObstacle?.points.length) {
      meshClearanceObstacles.push(meshObstacle);
    }

    if (geometry.type !== GeometryType.MESH || !analysis) {
      siblingGeometries.push(
        transformGeometryToTargetLinkFrame(geometry, sourceLinkMatrix, currentLinkInverseMatrix),
      );
      return;
    }

    const boxedGeometry = convertGeometryType(geometry, GeometryType.BOX, analysis);
    siblingGeometries.push(
      transformGeometryToTargetLinkFrame(
        {
          ...geometry,
          type: GeometryType.BOX,
          dimensions: { ...boxedGeometry.dimensions },
          origin: {
            xyz: { ...boxedGeometry.origin.xyz },
            rpy: { ...boxedGeometry.origin.rpy },
          },
          meshPath: undefined,
        },
        sourceLinkMatrix,
        currentLinkInverseMatrix,
      ),
    );
  });

  return {
    siblingGeometries: siblingGeometries.length > 0 ? siblingGeometries : undefined,
    meshClearanceObstacles: meshClearanceObstacles.length > 0 ? meshClearanceObstacles : undefined,
  };
}
