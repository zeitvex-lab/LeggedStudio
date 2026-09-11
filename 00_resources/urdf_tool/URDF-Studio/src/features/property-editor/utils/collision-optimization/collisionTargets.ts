import { getCollisionGeometryEntries } from '@/core/robot';
import type { AssemblyState, RobotData, UrdfVisual } from '@/types';
import { GeometryType } from '@/types';

export type CollisionOptimizationSource =
  | { kind: 'robot'; robot: RobotData }
  | { kind: 'assembly'; assembly: AssemblyState };

export type CollisionOptimizationScope = 'all' | 'mesh' | 'primitive' | 'selected';

export interface CollisionTargetRef {
  id: string;
  componentId?: string;
  componentName?: string;
  linkId: string;
  linkName: string;
  objectIndex: number;
  bodyIndex: number | null;
  geometry: UrdfVisual;
  isPrimary: boolean;
  sequenceIndex: number;
}

export interface CollisionTargetFilterSettings {
  scope: CollisionOptimizationScope;
  selectedTargetId?: string | null;
}

export function createCollisionTargetId(
  componentId: string | undefined,
  linkId: string,
  objectIndex: number,
): string {
  return `${componentId ?? 'robot'}::${linkId}::${objectIndex}`;
}

export function getCollisionTargetLinkGroupKey(
  target: Pick<CollisionTargetRef, 'componentId' | 'linkId'>,
): string {
  return `${target.componentId ?? 'robot'}::${target.linkId}`;
}

export function cloneCollisionGeometry(geometry: UrdfVisual): UrdfVisual {
  return {
    ...geometry,
    dimensions: { ...geometry.dimensions },
    origin: {
      xyz: { ...geometry.origin.xyz },
      rpy: { ...geometry.origin.rpy },
    },
  };
}

export function normalizeCollisionGeometry(geometry: UrdfVisual): UrdfVisual {
  return {
    ...cloneCollisionGeometry(geometry),
    dimensions: {
      x: Number.isFinite(geometry.dimensions?.x) ? geometry.dimensions.x : 0,
      y: Number.isFinite(geometry.dimensions?.y) ? geometry.dimensions.y : 0,
      z: Number.isFinite(geometry.dimensions?.z) ? geometry.dimensions.z : 0,
    },
    origin: {
      xyz: {
        x: Number.isFinite(geometry.origin?.xyz?.x) ? geometry.origin.xyz.x : 0,
        y: Number.isFinite(geometry.origin?.xyz?.y) ? geometry.origin.xyz.y : 0,
        z: Number.isFinite(geometry.origin?.xyz?.z) ? geometry.origin.xyz.z : 0,
      },
      rpy: {
        r: Number.isFinite(geometry.origin?.rpy?.r) ? geometry.origin.rpy.r : 0,
        p: Number.isFinite(geometry.origin?.rpy?.p) ? geometry.origin.rpy.p : 0,
        y: Number.isFinite(geometry.origin?.rpy?.y) ? geometry.origin.rpy.y : 0,
      },
    },
  };
}

function buildCollisionTargetsForRobot(
  robot: RobotData,
  componentMeta?: { componentId: string; componentName: string },
): CollisionTargetRef[] {
  const targets: CollisionTargetRef[] = [];

  Object.values(robot.links).forEach((link) => {
    const entries = getCollisionGeometryEntries(link);
    entries.forEach((entry, index) => {
      targets.push({
        id: createCollisionTargetId(componentMeta?.componentId, link.id, entry.objectIndex),
        componentId: componentMeta?.componentId,
        componentName: componentMeta?.componentName,
        linkId: link.id,
        linkName: link.name,
        objectIndex: entry.objectIndex,
        bodyIndex: entry.bodyIndex,
        geometry: cloneCollisionGeometry(entry.geometry),
        isPrimary: entry.bodyIndex === null,
        sequenceIndex: index,
      });
    });
  });

  return targets;
}

export function collectCollisionTargets(source: CollisionOptimizationSource): CollisionTargetRef[] {
  if (source.kind === 'robot') {
    return buildCollisionTargetsForRobot(source.robot);
  }

  return Object.values(source.assembly.components).flatMap((component) =>
    buildCollisionTargetsForRobot(component.robot, {
      componentId: component.id,
      componentName: component.name,
    }),
  );
}

export function filterCollisionTargets(
  targets: CollisionTargetRef[],
  settings: CollisionTargetFilterSettings,
): CollisionTargetRef[] {
  if (settings.scope === 'selected') {
    return settings.selectedTargetId
      ? targets.filter((target) => target.id === settings.selectedTargetId)
      : [];
  }

  if (settings.scope === 'mesh') {
    return targets.filter((target) => target.geometry.type === GeometryType.MESH);
  }

  if (settings.scope === 'primitive') {
    return targets.filter((target) => target.geometry.type !== GeometryType.MESH);
  }

  return targets;
}
