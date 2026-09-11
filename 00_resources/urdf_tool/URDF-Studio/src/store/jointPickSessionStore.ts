import { create } from 'zustand';

import type { SnapPointKind } from '@/core/geometry/meshSnapPoints';

export type { SnapPointKind };

export type JointPickSide = 'parent' | 'child';
export type JointPositionMode = 'simple' | 'twoPlanes' | 'twoEdges';

/** A committed joint-origin pick for one side. Matrices are serialized as 16-element
 * column-major arrays so the store never holds live THREE objects. */
export interface PickedSnapFrame {
  side: JointPickSide;
  componentId: string;
  linkId: string;
  kind: SnapPointKind;
  pointWorld: { x: number; y: number; z: number };
  poseWorldMatrix: number[];
  linkWorldMatrix: number[];
}

/** An intermediate feature pick used by the twoPlanes / twoEdges modes. */
export interface PendingFeatureSample {
  componentId: string;
  linkId: string;
  linkWorldMatrix: number[];
  point: { x: number; y: number; z: number };
  /** Present for plane samples (twoPlanes). */
  normal?: { x: number; y: number; z: number };
  /** Present for edge samples (twoEdges). */
  direction?: { x: number; y: number; z: number };
}

interface JointPickSessionState {
  active: boolean;
  side: JointPickSide;
  mode: JointPositionMode;
  snapFilter: SnapPointKind[] | null;
  /** Owning component + link per side, mirrored from the bridge draft relation so
   * the pick layer can reject hits on the wrong component or link. */
  parentComponentId: string | null;
  parentLinkId: string | null;
  childComponentId: string | null;
  childLinkId: string | null;
  pending: PendingFeatureSample[];
  parentSnap: PickedSnapFrame | null;
  childSnap: PickedSnapFrame | null;
  startPick: (side: JointPickSide) => void;
  setActive: (active: boolean) => void;
  setMode: (mode: JointPositionMode) => void;
  setSnapFilter: (filter: SnapPointKind[] | null) => void;
  setRelation: (
    parentComponentId: string | null,
    parentLinkId: string | null,
    childComponentId: string | null,
    childLinkId: string | null,
  ) => void;
  pushPending: (sample: PendingFeatureSample) => void;
  clearPending: () => void;
  commitSnap: (frame: PickedSnapFrame) => void;
  clearSide: (side: JointPickSide) => void;
  reset: () => void;
}

function createInitialSessionState() {
  return {
    active: false,
    side: 'parent' as JointPickSide,
    mode: 'simple' as JointPositionMode,
    snapFilter: null as SnapPointKind[] | null,
    parentComponentId: null as string | null,
    parentLinkId: null as string | null,
    childComponentId: null as string | null,
    childLinkId: null as string | null,
    pending: [] as PendingFeatureSample[],
    parentSnap: null as PickedSnapFrame | null,
    childSnap: null as PickedSnapFrame | null,
  };
}

// The store is the cross-feature handoff boundary, so it owns its data: clone
// the (serializable) matrices/points on write to insulate state from any later
// mutation of the caller's THREE-derived scratch objects.
function cloneSnapFrame(frame: PickedSnapFrame): PickedSnapFrame {
  return {
    ...frame,
    pointWorld: { ...frame.pointWorld },
    poseWorldMatrix: [...frame.poseWorldMatrix],
    linkWorldMatrix: [...frame.linkWorldMatrix],
  };
}

function clonePendingSample(sample: PendingFeatureSample): PendingFeatureSample {
  return {
    ...sample,
    linkWorldMatrix: [...sample.linkWorldMatrix],
    point: { ...sample.point },
    normal: sample.normal ? { ...sample.normal } : undefined,
    direction: sample.direction ? { ...sample.direction } : undefined,
  };
}

export const useJointPickSessionStore = create<JointPickSessionState>()((set) => ({
  ...createInitialSessionState(),
  startPick: (side) => set({ active: true, side, pending: [] }),
  setActive: (active) =>
    set((state) => (state.active === active ? state : { active, pending: [] })),
  setMode: (mode) => set((state) => (state.mode === mode ? state : { mode, pending: [] })),
  setSnapFilter: (snapFilter) => set({ snapFilter: snapFilter ? [...snapFilter] : null }),
  setRelation: (parentComponentId, parentLinkId, childComponentId, childLinkId) =>
    set((state) => {
      if (
        state.parentComponentId === parentComponentId &&
        state.parentLinkId === parentLinkId &&
        state.childComponentId === childComponentId &&
        state.childLinkId === childLinkId
      ) {
        return state;
      }

      // Drop a committed snap whose side relation changed; it would otherwise
      // align against a stale component/link.
      const parentChanged =
        (state.parentComponentId !== parentComponentId || state.parentLinkId !== parentLinkId) &&
        !(
          state.parentSnap &&
          state.parentSnap.componentId === parentComponentId &&
          state.parentSnap.linkId === parentLinkId
        );
      const childChanged =
        (state.childComponentId !== childComponentId || state.childLinkId !== childLinkId) &&
        !(
          state.childSnap &&
          state.childSnap.componentId === childComponentId &&
          state.childSnap.linkId === childLinkId
        );

      return {
        parentComponentId,
        parentLinkId,
        childComponentId,
        childLinkId,
        parentSnap: parentChanged ? null : state.parentSnap,
        childSnap: childChanged ? null : state.childSnap,
      };
    }),
  pushPending: (sample) =>
    set((state) => ({ pending: [...state.pending, clonePendingSample(sample)] })),
  clearPending: () => set((state) => (state.pending.length === 0 ? state : { pending: [] })),
  commitSnap: (frame) =>
    set(
      frame.side === 'parent'
        ? {
            parentComponentId: frame.componentId,
            parentLinkId: frame.linkId,
            parentSnap: cloneSnapFrame(frame),
            side: 'child',
            pending: [],
          }
        : {
            childComponentId: frame.componentId,
            childLinkId: frame.linkId,
            childSnap: cloneSnapFrame(frame),
            side: 'parent',
            pending: [],
          },
    ),
  clearSide: (side) =>
    set(side === 'parent' ? { parentSnap: null, pending: [] } : { childSnap: null, pending: [] }),
  reset: () => set(createInitialSessionState()),
}));
