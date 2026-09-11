import { useCallback } from 'react';

import { updateCollisionGeometryByObjectIndex } from '@/core/robot';
import type { PendingCollisionTransform } from '@/store/collisionTransformStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { WorkspaceLinkPropertyPatch } from '@/store/workspaceStore';
import type { LinkEntityRef } from '@/types';
import type { UpdateCommitMode, UpdateCommitOptions } from '@/types/viewer';

interface CollisionTransformParams {
  setPendingCollisionTransform: (transform: PendingCollisionTransform) => void;
  clearPendingCollisionTransform: () => void;
  handleTransformPendingChange: (pending: boolean) => void;
  applyUpdate: (
    ref: LinkEntityRef,
    data: WorkspaceLinkPropertyPatch,
    options?: UpdateCommitOptions,
  ) => void;
}

export function useCollisionTransformHandlers({
  setPendingCollisionTransform,
  clearPendingCollisionTransform,
  handleTransformPendingChange,
  applyUpdate,
}: CollisionTransformParams) {
  const applyCollisionTransformUpdate = useCallback(
    (
      ref: LinkEntityRef,
      position: { x: number; y: number; z: number },
      rotation: { r: number; p: number; y: number },
      commitMode: UpdateCommitMode,
      objectIndex = 0,
    ) => {
      const link = useWorkspaceStore.getState().workspace.components[
        ref.componentId
      ]?.robot.links[ref.entityId];
      if (!link) {
        return;
      }

      const updatedLink = updateCollisionGeometryByObjectIndex(link, objectIndex, {
        origin: { xyz: position, rpy: rotation },
      });
      applyUpdate(ref, updatedLink, {
        historyKey: `collision-transform:${ref.componentId}:${ref.entityId}:${objectIndex}`,
        historyLabel: 'Transform collision body',
        commitMode,
      });
    },
    [applyUpdate],
  );

  const handleCollisionTransformPreview = useCallback(
    (
      ref: LinkEntityRef,
      position: { x: number; y: number; z: number },
      rotation: { r: number; p: number; y: number },
      objectIndex = 0,
    ) => {
      setPendingCollisionTransform({
        componentId: ref.componentId,
        linkId: ref.entityId,
        objectIndex,
        position,
        rotation,
      });
    },
    [setPendingCollisionTransform],
  );

  const handleCollisionTransform = useCallback(
    (
      ref: LinkEntityRef,
      position: { x: number; y: number; z: number },
      rotation: { r: number; p: number; y: number },
      objectIndex = 0,
    ) => {
      clearPendingCollisionTransform();
      applyCollisionTransformUpdate(ref, position, rotation, 'immediate', objectIndex);
    },
    [applyCollisionTransformUpdate, clearPendingCollisionTransform],
  );

  const handleCollisionTransformPendingChange = useCallback(
    (pending: boolean) => {
      handleTransformPendingChange(pending);
      if (!pending) {
        clearPendingCollisionTransform();
      }
    },
    [clearPendingCollisionTransform, handleTransformPendingChange],
  );

  return {
    applyCollisionTransformUpdate,
    handleCollisionTransformPreview,
    handleCollisionTransform,
    handleCollisionTransformPendingChange,
  };
}
