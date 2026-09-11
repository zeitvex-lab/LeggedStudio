import type { UrdfLink } from '@/types';

export function hasLinkInertialChanged(
  previous: UrdfLink['inertial'] | undefined,
  next: UrdfLink['inertial'] | undefined,
): boolean {
  return JSON.stringify(previous ?? null) !== JSON.stringify(next ?? null);
}
