import { JointType, type UrdfJoint, type UrdfLink, type UrdfVisual } from '@/types';
import {
  parseGeneratedMjcfBodyIndex,
  parseGeneratedMjcfObjectName,
} from '@/core/parsers/mjcf/mjcfGeneratedNames';

const MJCF_GENERATED_OBJECT_NAME = /::(?:geom|site)(?:_\d+|\[\d+\])$/i;

function isGeneratedMjcfObjectLabelCandidate(name: string | null | undefined): boolean {
  const normalizedName = String(name || '').trim();
  if (!normalizedName) {
    return false;
  }

  if (MJCF_GENERATED_OBJECT_NAME.test(normalizedName)) {
    return true;
  }

  const parsed = parseGeneratedMjcfObjectName(normalizedName);
  return parsed != null && parseGeneratedMjcfBodyIndex(parsed.ownerName) != null;
}

function parseAnonymousBodyIndex(name: string | null | undefined): number | null {
  return parseGeneratedMjcfBodyIndex(name);
}

function toTitleCaseWords(value: string): string {
  return value.replace(/\b([a-z])/g, (match) => match.toUpperCase());
}

function normalizeDisplayLabelCandidate(value: string | null | undefined): string | null {
  const raw = String(value || '').trim();
  if (!raw || isGeneratedMjcfObjectLabelCandidate(raw)) {
    return null;
  }

  const withoutQuery = raw.split('?')[0] || raw;
  const fileName = withoutQuery.replace(/\\/g, '/').split('/').pop() || withoutQuery;
  const withoutExtension = fileName.replace(/\.[a-z0-9]+$/i, '');
  const spaced = withoutExtension
    .replace(/::/g, ' ')
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/([A-Za-z])(\d+)/g, '$1 $2')
    .replace(/(\d+)([A-Za-z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();

  if (!spaced) {
    return null;
  }

  return toTitleCaseWords(spaced);
}

function getVisualDisplayLabelCandidate(visual: UrdfVisual | null | undefined): string | null {
  if (!visual) {
    return null;
  }

  const candidates = [
    visual.name,
    visual.mjcfMesh?.name,
    visual.mjcfHfield?.name,
    visual.assetRef,
    visual.meshPath,
  ];

  for (const candidate of candidates) {
    const normalized = normalizeDisplayLabelCandidate(candidate);
    if (normalized) {
      return normalized;
    }
  }

  return null;
}

export function getMjcfLinkDisplayName(link: UrdfLink): string {
  const rawName = link.name?.trim() || link.id;
  const anonymousIndex = parseAnonymousBodyIndex(rawName);

  if (anonymousIndex == null) {
    return rawName;
  }

  const candidates = [
    getVisualDisplayLabelCandidate(link.visual),
    ...(link.visualBodies || []).map(getVisualDisplayLabelCandidate),
    getVisualDisplayLabelCandidate(link.collision),
    ...(link.collisionBodies || []).map(getVisualDisplayLabelCandidate),
  ];

  const preferred = candidates.find((candidate) => Boolean(candidate)) || null;
  if (preferred) {
    return anonymousIndex > 0 ? `${preferred} ${anonymousIndex + 1}` : preferred;
  }

  return `Body ${anonymousIndex + 1}`;
}

export function getMjcfRawDisplayName(
  rawName: string | null | undefined,
  fallbackOwnerDisplayName?: string | null,
): string {
  const normalizedRawName = String(rawName || '').trim();
  if (!normalizedRawName) {
    return '';
  }

  const generatedObjectMatch = parseGeneratedMjcfObjectName(normalizedRawName);
  const allowUnderscoreGeneratedObjectMatch =
    generatedObjectMatch != null &&
    (normalizedRawName.includes('::') ||
      Boolean(fallbackOwnerDisplayName) ||
      parseAnonymousBodyIndex(generatedObjectMatch.ownerName) != null);

  if (generatedObjectMatch && allowUnderscoreGeneratedObjectMatch) {
    const { ownerName, objectKind, index } = generatedObjectMatch;
    const ownerDisplayName = fallbackOwnerDisplayName || getMjcfRawDisplayName(ownerName);
    const kindDisplayName = objectKind === 'site' ? 'Site' : 'Geom';

    if (!ownerDisplayName) {
      return normalizedRawName;
    }

    return Number.isFinite(index)
      ? `${ownerDisplayName} ${kindDisplayName} ${index + 1}`
      : `${ownerDisplayName} ${kindDisplayName}`;
  }

  const anonymousIndex = parseAnonymousBodyIndex(normalizedRawName);
  if (anonymousIndex != null) {
    return `Body ${anonymousIndex + 1}`;
  }

  return normalizedRawName;
}

function isGeneratedImplicitFixedJointName(joint: UrdfJoint): boolean {
  if (joint.type !== JointType.FIXED) {
    return false;
  }

  const rawName = joint.name?.trim() || joint.id;
  const expectedBase = `${joint.parentLinkId}_to_${joint.childLinkId}`;
  return rawName === expectedBase || rawName.startsWith(`${expectedBase}_`);
}

export function getMjcfJointDisplayName(
  joint: UrdfJoint,
  parentLinkDisplayName: string,
  childLinkDisplayName: string,
): string {
  const rawName = joint.name?.trim() || joint.id;
  if (!isGeneratedImplicitFixedJointName(joint)) {
    return rawName;
  }

  const normalizedParent = parentLinkDisplayName === 'world' ? 'World' : parentLinkDisplayName;

  return `${normalizedParent} to ${childLinkDisplayName}`;
}
