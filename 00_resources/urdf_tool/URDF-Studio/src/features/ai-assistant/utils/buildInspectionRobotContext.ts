import {
  getMjcfJointDisplayName,
  getMjcfLinkDisplayName,
} from '@/shared/utils/robot/mjcfDisplayNames';
import type { RobotState } from '@/types';

const serializeGeometryForInspection = (geometry: RobotState['links'][string]['visual']) => ({
  origin: geometry.origin,
  geometry: {
    type: geometry.type,
    dimensions: geometry.dimensions,
  },
});

export const buildInspectionRobotContext = (robot: RobotState) => {
  const sourceFormat = robot.inspectionContext?.sourceFormat;
  const linkDisplayNames = Object.fromEntries(
    Object.values(robot.links).map((link) => [
      link.id,
      sourceFormat === 'mjcf' ? getMjcfLinkDisplayName(link) : link.name,
    ]),
  );

  return {
    name: robot.name,
    links: Object.values(robot.links).map((link) => ({
      id: link.id,
      name: linkDisplayNames[link.id] || link.name,
      inertial: {
        mass: link.inertial?.mass ?? 0,
        origin: link.inertial?.origin,
        inertia: link.inertial?.inertia,
      },
      visual: serializeGeometryForInspection(link.visual),
      collision: serializeGeometryForInspection(link.collision),
      collisionBodies: link.collisionBodies?.map(serializeGeometryForInspection),
    })),
    joints: Object.values(robot.joints).map((joint) => ({
      id: joint.id,
      name:
        sourceFormat === 'mjcf'
          ? getMjcfJointDisplayName(
              joint,
              linkDisplayNames[joint.parentLinkId] || joint.parentLinkId,
              linkDisplayNames[joint.childLinkId] || joint.childLinkId,
            )
          : joint.name,
      type: joint.type,
      parent: joint.parentLinkId,
      child: joint.childLinkId,
      origin: joint.origin,
      axis: joint.axis,
      limit: joint.limit,
      dynamics: joint.dynamics,
      hardware: joint.hardware,
      referencePosition: joint.referencePosition,
    })),
    rootId: robot.rootLinkId,
    inspectionContext: robot.inspectionContext,
  };
};
