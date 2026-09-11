import * as THREE from 'three';
import { createLoadingManager, createMeshLoader } from '@/core/loaders/meshLoader';
import { bakeColladaRootTransformInPlace, postProcessColladaScene } from '@/core/loaders';
import {
  buildColladaRootNormalizationHints,
  shouldNormalizeColladaGeometry,
  type ColladaRootNormalizationHints,
} from '@/core/loaders/colladaRootNormalization';
import { computeLinkWorldMatrices, getVisualGeometryEntries } from '@/core/robot';
import { GeometryType, type RenderableBounds, type RobotData, type UrdfVisual } from '@/types';
import { disposeObject3D } from '@/shared/utils/three/dispose';
import { mergeTextMeshSidecarAssets } from '@/core/loaders/textMeshAssetContext';

const IDENTITY_MATRIX = new THREE.Matrix4().identity();
const UNIT_BOX_GEOMETRY = new THREE.BoxGeometry(1, 1, 1);
const UNIT_PLANE_GEOMETRY = new THREE.PlaneGeometry(1, 1);
const UNIT_CYLINDER_GEOMETRY = new THREE.CylinderGeometry(1, 1, 1, 12, 1);
const UNIT_SPHERE_GEOMETRY = new THREE.SphereGeometry(1, 12, 12);

type GeometryBoundsDescriptor = {
  geometry: THREE.BufferGeometry;
  scale: THREE.Vector3;
  rotation: THREE.Euler;
  disposeAfterUse?: boolean;
};

function toFiniteOr(value: number | undefined, fallback: number): number {
  return Number.isFinite(value) ? Number(value) : fallback;
}

function createPrimitiveGeometryBoundsDescriptor(
  geometry: UrdfVisual,
): GeometryBoundsDescriptor | null {
  switch (geometry.type) {
    case GeometryType.BOX:
      return {
        geometry: UNIT_BOX_GEOMETRY,
        scale: new THREE.Vector3(
          toFiniteOr(geometry.dimensions.x, 0),
          toFiniteOr(geometry.dimensions.y, 0),
          toFiniteOr(geometry.dimensions.z, 0),
        ),
        rotation: new THREE.Euler(0, 0, 0, 'ZYX'),
      };
    case GeometryType.PLANE:
      return {
        geometry: UNIT_PLANE_GEOMETRY,
        scale: new THREE.Vector3(
          Math.max(toFiniteOr(geometry.dimensions.x, 1), 1e-6),
          Math.max(toFiniteOr(geometry.dimensions.y, 1), 1e-6),
          1,
        ),
        rotation: new THREE.Euler(0, 0, 0, 'ZYX'),
      };
    case GeometryType.CYLINDER:
      return {
        geometry: UNIT_CYLINDER_GEOMETRY,
        scale: new THREE.Vector3(
          Math.max(toFiniteOr(geometry.dimensions.x, 0), 0),
          Math.max(toFiniteOr(geometry.dimensions.y, 0), 0),
          Math.max(toFiniteOr(geometry.dimensions.z, geometry.dimensions.x), 0),
        ),
        rotation: new THREE.Euler(-Math.PI / 2, 0, 0, 'ZYX'),
      };
    case GeometryType.SPHERE:
    case GeometryType.ELLIPSOID:
      return {
        geometry: UNIT_SPHERE_GEOMETRY,
        scale: new THREE.Vector3(
          Math.max(toFiniteOr(geometry.dimensions.x, 0), 0),
          Math.max(toFiniteOr(geometry.dimensions.y, geometry.dimensions.x), 0),
          Math.max(toFiniteOr(geometry.dimensions.z, geometry.dimensions.x), 0),
        ),
        rotation: new THREE.Euler(0, 0, 0, 'ZYX'),
      };
    case GeometryType.CAPSULE: {
      const radius = Math.max(toFiniteOr(geometry.dimensions.x, 0), 0);
      const totalLength = Math.max(toFiniteOr(geometry.dimensions.y, 0), 0);
      const cylinderLength = Math.max(0, totalLength - 2 * radius);
      return {
        geometry: new THREE.CapsuleGeometry(radius, cylinderLength, 4, 8),
        scale: new THREE.Vector3(1, 1, 1),
        rotation: new THREE.Euler(-Math.PI / 2, 0, 0, 'ZYX'),
        disposeAfterUse: true,
      };
    }
    default:
      return null;
  }
}

function buildGeometryOriginMatrix(geometry: UrdfVisual): THREE.Matrix4 {
  const origin = geometry.origin ?? {
    xyz: { x: 0, y: 0, z: 0 },
    rpy: { r: 0, p: 0, y: 0 },
  };

  return new THREE.Matrix4().compose(
    new THREE.Vector3(
      toFiniteOr(origin.xyz?.x, 0),
      toFiniteOr(origin.xyz?.y, 0),
      toFiniteOr(origin.xyz?.z, 0),
    ),
    new THREE.Quaternion().setFromEuler(
      new THREE.Euler(
        toFiniteOr(origin.rpy?.r, 0),
        toFiniteOr(origin.rpy?.p, 0),
        toFiniteOr(origin.rpy?.y, 0),
        'ZYX',
      ),
    ),
    new THREE.Vector3(1, 1, 1),
  );
}

function unionBounds(
  target: THREE.Box3,
  source: THREE.Box3,
  hasBounds: { current: boolean },
): void {
  if (!hasBounds.current) {
    target.copy(source);
    hasBounds.current = true;
    return;
  }

  target.union(source);
}

function appendPrimitiveGeometryBounds(
  target: THREE.Box3,
  hasBounds: { current: boolean },
  linkMatrix: THREE.Matrix4,
  geometry: UrdfVisual,
): void {
  const descriptor = createPrimitiveGeometryBoundsDescriptor(geometry);
  if (!descriptor) {
    return;
  }

  if (!descriptor.geometry.boundingBox) {
    descriptor.geometry.computeBoundingBox();
  }

  const geometryBox = descriptor.geometry.boundingBox;
  if (!geometryBox) {
    if (descriptor.disposeAfterUse) {
      descriptor.geometry.dispose();
    }
    return;
  }

  const originMatrix = buildGeometryOriginMatrix(geometry);
  const childMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(0, 0, 0),
    new THREE.Quaternion().setFromEuler(descriptor.rotation),
    descriptor.scale,
  );
  const worldMatrix = linkMatrix.clone().multiply(originMatrix).multiply(childMatrix);
  unionBounds(target, geometryBox.clone().applyMatrix4(worldMatrix), hasBounds);

  if (descriptor.disposeAfterUse) {
    descriptor.geometry.dispose();
  }
}

async function loadMeshGeometryBounds(
  geometry: UrdfVisual,
  meshScale: { x: number; y: number; z: number },
  manager: THREE.LoadingManager,
  meshLoader: ReturnType<typeof createMeshLoader>,
  colladaRootNormalizationHints: ColladaRootNormalizationHints | null,
): Promise<THREE.Box3 | null> {
  return await new Promise<THREE.Box3 | null>((resolve) => {
    const meshPath = geometry.meshPath ?? '';
    void meshLoader(meshPath, manager, (object, error) => {
      if (error) {
        // Mesh resolution failures (e.g. USD inline meshes whose virtual
        // .obj paths are never present in the asset pool) must not abort the
        // whole renderable-bounds computation. The meshLoader already logs
        // the failure via logRuntimeFailure; treat the geometry as having
        // no bounds so the component can still be inserted.
        resolve(null);
        return;
      }

      if (
        !object ||
        (object as THREE.Object3D & { userData?: { isPlaceholder?: boolean } }).userData
          ?.isPlaceholder
      ) {
        resolve(null);
        return;
      }

      if (meshPath.toLowerCase().endsWith('.dae')) {
        postProcessColladaScene(object);
        if (
          shouldNormalizeColladaGeometry(meshPath, geometry.origin, colladaRootNormalizationHints)
        ) {
          bakeColladaRootTransformInPlace(object);
        } else {
          object.rotation.set(0, 0, 0);
          object.updateMatrix();
        }
      }

      const scaleWrapper = new THREE.Group();
      scaleWrapper.scale.set(meshScale.x, meshScale.y, meshScale.z);
      scaleWrapper.add(object);
      scaleWrapper.updateMatrixWorld(true);

      const bounds = new THREE.Box3().setFromObject(scaleWrapper);
      disposeObject3D(scaleWrapper, true);
      resolve(bounds.isEmpty() ? null : bounds);
    });
  });
}

async function appendRenderableGeometryBounds(
  target: THREE.Box3,
  hasBounds: { current: boolean },
  linkMatrix: THREE.Matrix4,
  geometry: UrdfVisual,
  context: {
    manager: THREE.LoadingManager;
    meshLoader: ReturnType<typeof createMeshLoader>;
    meshBoundsCache: Map<string, Promise<THREE.Box3 | null>>;
    colladaRootNormalizationHints: ColladaRootNormalizationHints | null;
  },
): Promise<void> {
  if (geometry.type !== GeometryType.MESH || !geometry.meshPath) {
    appendPrimitiveGeometryBounds(target, hasBounds, linkMatrix, geometry);
    return;
  }

  const scale = {
    x: Math.max(toFiniteOr(geometry.dimensions.x, 1), 1e-6),
    y: Math.max(toFiniteOr(geometry.dimensions.y, 1), 1e-6),
    z: Math.max(toFiniteOr(geometry.dimensions.z, 1), 1e-6),
  };
  const cacheKey = `${geometry.meshPath}|${scale.x}|${scale.y}|${scale.z}|${String(
    shouldNormalizeColladaGeometry(
      geometry.meshPath,
      geometry.origin,
      context.colladaRootNormalizationHints,
    ),
  )}`;
  let pendingBounds = context.meshBoundsCache.get(cacheKey);

  if (!pendingBounds) {
    pendingBounds = loadMeshGeometryBounds(
      geometry,
      scale,
      context.manager,
      context.meshLoader,
      context.colladaRootNormalizationHints,
    );
    context.meshBoundsCache.set(cacheKey, pendingBounds);
  }

  const localBounds = await pendingBounds;
  if (!localBounds) {
    return;
  }

  const originMatrix = buildGeometryOriginMatrix(geometry);
  const worldMatrix = linkMatrix.clone().multiply(originMatrix);
  unionBounds(target, localBounds.clone().applyMatrix4(worldMatrix), hasBounds);
}

function toRenderableBounds(bounds: THREE.Box3 | null): RenderableBounds | null {
  if (!bounds || bounds.isEmpty()) {
    return null;
  }

  return {
    min: { x: bounds.min.x, y: bounds.min.y, z: bounds.min.z },
    max: { x: bounds.max.x, y: bounds.max.y, z: bounds.max.z },
  };
}

export async function computeRobotRenderableBoundsFromAssets(
  robot: RobotData,
  assets: Record<string, string> | null | undefined,
  allFileContents: Record<string, string> | null | undefined = undefined,
): Promise<RenderableBounds | null> {
  const effectiveAssets = mergeTextMeshSidecarAssets(assets ?? {}, allFileContents ?? {});

  if (Object.keys(effectiveAssets).length === 0) {
    return null;
  }

  const linkWorldMatrices = computeLinkWorldMatrices(robot);
  const manager = createLoadingManager(effectiveAssets, '');
  const meshLoader = createMeshLoader(effectiveAssets, manager);
  const meshBoundsCache = new Map<string, Promise<THREE.Box3 | null>>();
  const context = {
    manager,
    meshLoader,
    meshBoundsCache,
    colladaRootNormalizationHints: buildColladaRootNormalizationHints(robot.links),
  };

  const linkBoundsList = await Promise.all(
    Object.entries(robot.links).map(async ([linkId, link]) => {
      const linkMatrix = linkWorldMatrices[linkId] ?? IDENTITY_MATRIX;
      const visualBounds = new THREE.Box3();
      const visualHasBounds = { current: false };

      await Promise.all(
        getVisualGeometryEntries(link).map(async (entry) => {
          await appendRenderableGeometryBounds(
            visualBounds,
            visualHasBounds,
            linkMatrix,
            entry.geometry,
            context,
          );
        }),
      );

      if (visualHasBounds.current) {
        return visualBounds;
      }

      const collisionBounds = new THREE.Box3();
      const collisionHasBounds = { current: false };
      const collisionGeometries = [
        ...(link.collision.type !== GeometryType.NONE ? [link.collision] : []),
        ...(link.collisionBodies ?? []).filter((body) => body.type !== GeometryType.NONE),
      ];

      await Promise.all(
        collisionGeometries.map(async (geometry) => {
          await appendRenderableGeometryBounds(
            collisionBounds,
            collisionHasBounds,
            linkMatrix,
            geometry,
            context,
          );
        }),
      );

      return collisionHasBounds.current ? collisionBounds : null;
    }),
  );

  const resolvedBounds = new THREE.Box3();
  const hasResolvedBounds = { current: false };
  linkBoundsList.forEach((linkBounds) => {
    if (!linkBounds) {
      return;
    }
    unionBounds(resolvedBounds, linkBounds, hasResolvedBounds);
  });

  return toRenderableBounds(hasResolvedBounds.current ? resolvedBounds : null);
}
