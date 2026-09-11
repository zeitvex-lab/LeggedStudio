import { JointType, type BridgeJoint } from '@/types';

type AssemblyBridgeTopologyEdge = Pick<
  BridgeJoint,
  'id' | 'parentComponentId' | 'childComponentId'
>;

export function buildAssemblyParentByChildComponentId(
  bridges: Iterable<AssemblyBridgeTopologyEdge>,
  options?: { ignoreBridgeId?: string },
): Map<string, string> {
  const parentByChildComponentId = new Map<string, string>();

  for (const bridge of bridges) {
    if (bridge.id === options?.ignoreBridgeId) {
      continue;
    }

    if (!parentByChildComponentId.has(bridge.childComponentId)) {
      parentByChildComponentId.set(bridge.childComponentId, bridge.parentComponentId);
    }
  }

  return parentByChildComponentId;
}

export function wouldCreateAssemblyComponentCycle(
  parentByChildComponentId: Map<string, string>,
  parentComponentId: string,
  childComponentId: string,
): boolean {
  let currentComponentId: string | undefined = parentComponentId;

  while (currentComponentId) {
    if (currentComponentId === childComponentId) {
      return true;
    }

    currentComponentId = parentByChildComponentId.get(currentComponentId);
  }

  return false;
}

export function wouldBridgeCreateUnsupportedAssemblyCycle(
  bridges: Iterable<AssemblyBridgeTopologyEdge>,
  bridge: AssemblyBridgeTopologyEdge,
  jointType: JointType,
  options?: { ignoreBridgeId?: string },
): boolean {
  if (jointType === JointType.FIXED) {
    return false;
  }

  return wouldCreateAssemblyComponentCycle(
    buildAssemblyParentByChildComponentId(bridges, options),
    bridge.parentComponentId,
    bridge.childComponentId,
  );
}
