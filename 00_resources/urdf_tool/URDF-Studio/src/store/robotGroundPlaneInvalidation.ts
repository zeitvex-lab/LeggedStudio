import { useWorkspaceStore } from './workspaceStore';

export type GroundPlaneInvalidationListener = () => void;
export type GroundPlaneInvalidationSubscription = (
  listener: GroundPlaneInvalidationListener,
) => () => void;

export const subscribeWorkspaceGroundPlaneInvalidation: GroundPlaneInvalidationSubscription = (
  listener,
) =>
  useWorkspaceStore.subscribe((state, previousState) => {
    if (state.revision !== previousState.revision) {
      listener();
    }
  });
