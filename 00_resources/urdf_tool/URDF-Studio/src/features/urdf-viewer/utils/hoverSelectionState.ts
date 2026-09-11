import type * as THREE from 'three';

import type { ResolvedHoverMatch } from './hoverLinkBounds.ts';

export interface HoverSelectionMatchMeta {
  linkId: string;
  highlightTarget?: THREE.Object3D | null;
  objectIndex?: number;
}

export interface HoverSelectionState {
  linkId: string | null;
  highlightTarget: THREE.Object3D | null;
  objectIndex?: number;
}

export function resolveHoverSelectionState(
  preferredHoverMatch: ResolvedHoverMatch<HoverSelectionMatchMeta> | null,
): HoverSelectionState {
  if (!preferredHoverMatch) {
    return {
      linkId: null,
      highlightTarget: null,
      objectIndex: undefined,
    };
  }

  return {
    linkId: preferredHoverMatch.match.meta.linkId,
    highlightTarget: preferredHoverMatch.match.meta.highlightTarget ?? null,
    objectIndex: preferredHoverMatch.match.meta.objectIndex,
  };
}
