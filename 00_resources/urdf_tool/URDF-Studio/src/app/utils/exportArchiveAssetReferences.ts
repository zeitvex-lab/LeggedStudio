import { collectGeometryTexturePaths, getVisualGeometryEntries } from '@/core/robot';
import { GeometryType, type RobotState, type UrdfLink } from '@/types';

export function collectRobotAssetReferences(robot: RobotState): {
  meshPaths: Set<string>;
  texturePaths: Set<string>;
} {
  const meshPaths = new Set<string>();
  const texturePaths = new Set<string>();

  Object.values(robot.links).forEach((link: UrdfLink) => {
    getVisualGeometryEntries(link).forEach((entry) => {
      if (entry.geometry.type === GeometryType.MESH && entry.geometry.meshPath) {
        meshPaths.add(entry.geometry.meshPath);
      }
      collectGeometryTexturePaths(entry.geometry).forEach((texturePath) => {
        texturePaths.add(texturePath);
      });
    });
    if (link.collision && link.collision.type === GeometryType.MESH && link.collision.meshPath) {
      meshPaths.add(link.collision.meshPath);
    }
    (link.collisionBodies || []).forEach((body) => {
      if (body.type === GeometryType.MESH && body.meshPath) {
        meshPaths.add(body.meshPath);
      }
    });
  });

  Object.values(robot.materials || {}).forEach((material) => {
    if (material.texture) {
      texturePaths.add(material.texture);
    }
  });

  return {
    meshPaths,
    texturePaths,
  };
}
