import { applyWorkspaceLinkPropertyPatch } from '@/store/workspace/propertyPatches';
import type { WorkspaceLinkPropertyPatch } from '@/store/workspaceStore';
import type { UrdfLink } from '@/types';

/** Shared deep property-patch contract; store and app previews use identical semantics. */
export function applyLinkPatch(
  currentLink: UrdfLink,
  patch: WorkspaceLinkPropertyPatch,
): UrdfLink {
  return applyWorkspaceLinkPropertyPatch(currentLink, patch);
}
