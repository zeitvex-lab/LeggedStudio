import {
  getPreferredSingleMaterialFromBoxFacePalette,
  getVisualGeometryByObjectIndex,
  getVisualGeometryEntries,
  updateVisualGeometryByObjectIndex,
} from '@/core/robot';
import type { RobotState } from '@/types';

export interface BoxFaceMaterialExportFallbackRecord {
  linkId: string;
  linkName: string;
  objectIndex: number;
  chosenFace: string;
}

export interface BoxFaceMaterialExportFallbackResult {
  robot: RobotState;
  records: BoxFaceMaterialExportFallbackRecord[];
}

export function applyBoxFaceMaterialExportFallback(
  robot: RobotState,
): BoxFaceMaterialExportFallbackResult {
  let nextLinks = robot.links;
  const records: BoxFaceMaterialExportFallbackRecord[] = [];

  Object.entries(robot.links).forEach(([linkId, link]) => {
    let nextLink = link;
    let linkChanged = false;

    getVisualGeometryEntries(link).forEach((entry) => {
      const currentGeometry =
        getVisualGeometryByObjectIndex(nextLink, entry.objectIndex)?.geometry ?? entry.geometry;
      const preferredMaterial = getPreferredSingleMaterialFromBoxFacePalette(currentGeometry);
      if (!preferredMaterial) {
        return;
      }

      nextLink = updateVisualGeometryByObjectIndex(nextLink, entry.objectIndex, {
        authoredMaterials: [preferredMaterial.material],
      });
      linkChanged = true;
      records.push({
        linkId,
        linkName: link.name || linkId,
        objectIndex: entry.objectIndex,
        chosenFace: preferredMaterial.face,
      });
    });

    if (!linkChanged) {
      return;
    }

    if (nextLinks === robot.links) {
      nextLinks = { ...robot.links };
    }
    nextLinks[linkId] = nextLink;
  });

  return {
    robot: nextLinks === robot.links ? robot : { ...robot, links: nextLinks },
    records,
  };
}
