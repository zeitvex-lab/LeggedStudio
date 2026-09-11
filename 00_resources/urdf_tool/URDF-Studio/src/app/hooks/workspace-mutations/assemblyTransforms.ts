import { cloneAssemblyTransform } from '@/core/robot/assemblyTransformUtils';
import type { AssemblyTransform } from '@/types';

export function areAssemblyTransformsEqual(
  left?: AssemblyTransform | null,
  right?: AssemblyTransform | null,
): boolean {
  const normalizedLeft = cloneAssemblyTransform(left);
  const normalizedRight = cloneAssemblyTransform(right);

  return (
    normalizedLeft.position.x === normalizedRight.position.x &&
    normalizedLeft.position.y === normalizedRight.position.y &&
    normalizedLeft.position.z === normalizedRight.position.z &&
    normalizedLeft.rotation.r === normalizedRight.rotation.r &&
    normalizedLeft.rotation.p === normalizedRight.rotation.p &&
    normalizedLeft.rotation.y === normalizedRight.rotation.y
  );
}
