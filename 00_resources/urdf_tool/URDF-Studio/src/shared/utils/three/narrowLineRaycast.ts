import * as THREE from 'three';

const DEFAULT_NARROW_LINE_THRESHOLD = 0.08;

export function createNarrowLineRaycast(
  threshold = DEFAULT_NARROW_LINE_THRESHOLD,
): THREE.Object3D['raycast'] {
  return function narrowLineRaycast(
    this: THREE.Object3D,
    raycaster: THREE.Raycaster,
    intersects: THREE.Intersection[],
  ) {
    const previousThreshold = raycaster.params.Line.threshold;
    raycaster.params.Line.threshold = threshold;

    try {
      THREE.Line.prototype.raycast.call(
        this as unknown as THREE.Line,
        raycaster,
        intersects as THREE.Intersection<THREE.Object3D>[],
      );
    } finally {
      raycaster.params.Line.threshold = previousThreshold;
    }
  };
}

export const narrowLineRaycast = createNarrowLineRaycast();
