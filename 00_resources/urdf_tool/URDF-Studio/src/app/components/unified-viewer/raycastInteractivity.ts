import type { Group as ThreeGroup, Object3D as ThreeObject3D } from 'three';

export type RaycastableObject = ThreeObject3D & {
  raycast?: ThreeObject3D['raycast'];
};

const NOOP_RAYCAST: ThreeObject3D['raycast'] = () => {};

export function syncGroupRaycastInteractivity(
  root: ThreeGroup | null,
  interactive: boolean,
  originalRaycasts: WeakMap<RaycastableObject, NonNullable<RaycastableObject['raycast']>>,
) {
  if (!root) {
    return;
  }

  root.traverse((child) => {
    const raycastable = child as RaycastableObject;
    if (typeof raycastable.raycast !== 'function') {
      return;
    }

    if (interactive) {
      const originalRaycast = originalRaycasts.get(raycastable);
      if (originalRaycast && raycastable.raycast === NOOP_RAYCAST) {
        raycastable.raycast = originalRaycast;
      }
      return;
    }

    if (raycastable.raycast === NOOP_RAYCAST) {
      return;
    }

    originalRaycasts.set(raycastable, raycastable.raycast);
    raycastable.raycast = NOOP_RAYCAST;
  });
}
