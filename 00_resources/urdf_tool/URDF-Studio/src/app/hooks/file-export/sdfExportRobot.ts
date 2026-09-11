import {
  getVisualGeometryEntries,
  updateVisualGeometryByObjectIndex,
} from '@/core/robot';
import { colorRgbaTupleToHex } from '@/core/utils/color';
import type { RobotState, UrdfLink, UrdfVisualMaterial } from '@/types';

function normalizeHexColor(value: string | null | undefined): string | null {
  const raw = value?.trim().toLowerCase();
  if (!raw) {
    return null;
  }

  const normalized = raw.startsWith('#') ? raw : `#${raw}`;
  return /^#[0-9a-f]{6}$/i.test(normalized) ? normalized : null;
}

function shouldDropSdfColorRgba(material: UrdfVisualMaterial): boolean {
  if (!material.colorRgba || material.colorRgba[3] < 0.999) {
    return false;
  }

  const color = normalizeHexColor(material.color);
  return Boolean(color && colorRgbaTupleToHex(material.colorRgba) === color);
}

function normalizeSdfAuthoredMaterial(material: UrdfVisualMaterial): UrdfVisualMaterial {
  if (!shouldDropSdfColorRgba(material)) {
    return material;
  }

  const { colorRgba: _colorRgba, ...nextMaterial } = material;
  return nextMaterial;
}

function prepareLinkForSdfExport(link: UrdfLink): UrdfLink {
  return getVisualGeometryEntries(link).reduce((nextLink, entry) => {
    const authoredMaterials = entry.geometry.authoredMaterials;
    if (!authoredMaterials?.some(shouldDropSdfColorRgba)) {
      return nextLink;
    }

    return updateVisualGeometryByObjectIndex(nextLink, entry.objectIndex, {
      authoredMaterials: authoredMaterials.map(normalizeSdfAuthoredMaterial),
    });
  }, link);
}

export function prepareRobotForSdfExport(robot: RobotState): RobotState {
  let nextLinks = robot.links;

  Object.entries(robot.links).forEach(([linkId, link]) => {
    const nextLink = prepareLinkForSdfExport(link);
    if (nextLink === link) {
      return;
    }

    if (nextLinks === robot.links) {
      nextLinks = { ...robot.links };
    }
    nextLinks[linkId] = nextLink;
  });

  return nextLinks === robot.links ? robot : { ...robot, links: nextLinks };
}
