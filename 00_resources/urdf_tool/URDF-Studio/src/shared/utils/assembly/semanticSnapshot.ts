import type { AssemblyComponent, AssemblyState, BridgeJoint } from '@/types';

import {
  createStableJsonSnapshot,
  stripRobotPersistenceState,
  stripTransientJointMotionFromJoint,
} from '@/shared/utils/robot/semanticSnapshot';

function stripPersistenceStateFromComponent(component: AssemblyComponent) {
  const { visible: _visible, robot, ...sourceComponent } = component;
  return {
    ...sourceComponent,
    robot: stripRobotPersistenceState(robot),
  };
}

function stripPersistenceStateFromBridge(bridge: BridgeJoint): BridgeJoint {
  return {
    ...bridge,
    joint: stripTransientJointMotionFromJoint(bridge.joint),
  };
}

export function createAssemblyPersistenceSnapshot(assembly: AssemblyState | null): string {
  if (!assembly) {
    return createStableJsonSnapshot(null);
  }

  return createStableJsonSnapshot({
    ...assembly,
    components: Object.fromEntries(
      Object.entries(assembly.components).map(([componentId, component]) => [
        componentId,
        stripPersistenceStateFromComponent(component),
      ]),
    ),
    bridges: Object.fromEntries(
      Object.entries(assembly.bridges).map(([bridgeId, bridge]) => [
        bridgeId,
        stripPersistenceStateFromBridge(bridge),
      ]),
    ),
  });
}
