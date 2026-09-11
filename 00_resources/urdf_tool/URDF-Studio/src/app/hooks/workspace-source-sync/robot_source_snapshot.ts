import type { RobotState } from '@/types';

export type JsonLike =
  | null
  | boolean
  | number
  | string
  | JsonLike[]
  | { [key: string]: JsonLike };

export function sortKeysDeep(value: unknown): JsonLike {
  if (Array.isArray(value)) {
    return value.map((item) => sortKeysDeep(item));
  }

  if (value && typeof value === 'object') {
    return Object.keys(value)
      .sort((left, right) => left.localeCompare(right))
      .reduce<Record<string, JsonLike>>((acc, key) => {
        const nextValue = (value as Record<string, unknown>)[key];
        if (nextValue !== undefined) {
          acc[key] = sortKeysDeep(nextValue);
        }
        return acc;
      }, {});
  }

  if (
    value === null ||
    typeof value === 'boolean' ||
    typeof value === 'number' ||
    typeof value === 'string'
  ) {
    return value as JsonLike;
  }

  return null;
}

export function createRobotSourceSnapshot(robot: RobotState): string {
  return JSON.stringify(
    sortKeysDeep({
      name: robot.name,
      rootLinkId: robot.rootLinkId,
      links: robot.links,
      joints: robot.joints,
      materials: robot.materials ?? null,
      closedLoopConstraints: robot.closedLoopConstraints ?? null,
    }),
  );
}
