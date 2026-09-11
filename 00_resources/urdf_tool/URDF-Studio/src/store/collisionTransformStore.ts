import { create } from 'zustand';

export interface PendingCollisionTransform {
  componentId: string;
  linkId: string;
  objectIndex: number;
  position: { x: number; y: number; z: number };
  rotation: { r: number; p: number; y: number };
}

interface CollisionTransformState {
  pendingCollisionTransform: PendingCollisionTransform | null;
  setPendingCollisionTransform: (transform: PendingCollisionTransform) => void;
  clearPendingCollisionTransform: () => void;
}

function isSamePendingTransform(
  current: PendingCollisionTransform | null,
  next: PendingCollisionTransform,
): boolean {
  if (!current) return false;

  return current.componentId === next.componentId
    && current.linkId === next.linkId
    && current.objectIndex === next.objectIndex
    && current.position.x === next.position.x
    && current.position.y === next.position.y
    && current.position.z === next.position.z
    && current.rotation.r === next.rotation.r
    && current.rotation.p === next.rotation.p
    && current.rotation.y === next.rotation.y;
}

export const useCollisionTransformStore = create<CollisionTransformState>()((set) => ({
  pendingCollisionTransform: null,
  setPendingCollisionTransform: (transform) => set((state) => (
    isSamePendingTransform(state.pendingCollisionTransform, transform)
      ? state
      : { pendingCollisionTransform: transform }
  )),
  clearPendingCollisionTransform: () => set((state) => (
    state.pendingCollisionTransform === null
      ? state
      : { pendingCollisionTransform: null }
  )),
}));
