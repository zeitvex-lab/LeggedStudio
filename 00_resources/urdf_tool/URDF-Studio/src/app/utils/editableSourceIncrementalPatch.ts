import { syncRobotMaterialsForLinkUpdate } from '@/core/robot/materials';
import type { RobotData, RobotMaterialState, RobotState, UrdfJoint, UrdfLink } from '@/types';

export type EditableSourceIncrementalPatch =
  | {
      kind: 'urdf-link-fragment-update';
      previousLinkId: string;
      previousLinkName: string;
      nextLink: UrdfLink;
    }
  | {
      kind: 'urdf-joint-fragment-update';
      previousJointId: string;
      previousJointName: string;
      previousParentLinkId: string;
      previousChildLinkId: string;
      nextJoint: UrdfJoint;
    }
  | {
      kind: 'mjcf-body-subtree-update';
      stableLinkNames: string[];
      stableJointNames: string[];
      previousJointEndpointsByName: Record<string, { parentLinkId: string; childLinkId: string }>;
      nextLinksByName: Record<string, UrdfLink>;
      nextJointsByName: Record<string, UrdfJoint>;
    };

interface ApplyEditableSourceIncrementalPatchOptions {
  patch: EditableSourceIncrementalPatch;
  currentState: Pick<
    RobotData,
    | 'name'
    | 'version'
    | 'links'
    | 'joints'
    | 'rootLinkId'
    | 'materials'
    | 'closedLoopConstraints'
    | 'inspectionContext'
  >;
}

function preserveRuntimeLinkMetadata(nextLink: UrdfLink, currentLink: UrdfLink): UrdfLink {
  return {
    ...nextLink,
    id: currentLink.id,
    visible: currentLink.visible,
    visual: {
      ...nextLink.visual,
      visible: currentLink.visual.visible,
    },
    visualBodies: (nextLink.visualBodies ?? []).map((body, index) => ({
      ...body,
      visible: currentLink.visualBodies?.[index]?.visible,
    })),
    collision: {
      ...nextLink.collision,
      visible: currentLink.collision.visible,
    },
    collisionBodies: (nextLink.collisionBodies ?? []).map((body, index) => ({
      ...body,
      visible: currentLink.collisionBodies?.[index]?.visible,
    })),
  };
}

function preserveRuntimeJointMetadata(nextJoint: UrdfJoint, currentJoint: UrdfJoint): UrdfJoint {
  return {
    ...nextJoint,
    id: currentJoint.id,
    parentLinkId: currentJoint.parentLinkId,
    childLinkId: currentJoint.childLinkId,
    angle: currentJoint.angle,
    quaternion: currentJoint.quaternion,
  };
}

function resolveCurrentLinkKeyByName(
  links: Record<string, UrdfLink>,
  linkName: string,
): string | null {
  if (Object.prototype.hasOwnProperty.call(links, linkName)) {
    return linkName;
  }

  return Object.keys(links).find((linkId) => links[linkId]?.name === linkName) ?? null;
}

function resolveCurrentJointKeyByName(
  joints: Record<string, UrdfJoint>,
  jointName: string,
): string | null {
  if (Object.prototype.hasOwnProperty.call(joints, jointName)) {
    return jointName;
  }

  return Object.keys(joints).find((jointId) => joints[jointId]?.name === jointName) ?? null;
}

function resolveCurrentLinkKey(
  links: Record<string, UrdfLink>,
  linkId: string,
  linkName: string,
): string | null {
  return Object.prototype.hasOwnProperty.call(links, linkId)
    ? linkId
    : resolveCurrentLinkKeyByName(links, linkName);
}

function resolveCurrentJointKey(
  joints: Record<string, UrdfJoint>,
  jointId: string,
  jointName: string,
): string | null {
  return Object.prototype.hasOwnProperty.call(joints, jointId)
    ? jointId
    : resolveCurrentJointKeyByName(joints, jointName);
}

function applyLinkPatch(
  options: ApplyEditableSourceIncrementalPatchOptions,
): RobotState | null {
  const { currentState, patch } = options;
  if (patch.kind !== 'urdf-link-fragment-update') {
    return null;
  }

  const currentLinkKey = resolveCurrentLinkKey(
    currentState.links,
    patch.previousLinkId,
    patch.previousLinkName,
  );
  if (!currentLinkKey) {
    return null;
  }

  const currentLink = currentState.links[currentLinkKey];
  const patchedLink = preserveRuntimeLinkMetadata(patch.nextLink, currentLink);
  const nextMaterials = syncRobotMaterialsForLinkUpdate(
    currentState.materials,
    patchedLink,
    currentLink,
  );

  return {
    ...currentState,
    links: {
      ...currentState.links,
      [currentLinkKey]: patchedLink,
    },
    materials: nextMaterials,
    selection: { type: null, id: null },
  };
}

function applyJointPatch(
  options: ApplyEditableSourceIncrementalPatchOptions,
): RobotState | null {
  const { currentState, patch } = options;
  if (patch.kind !== 'urdf-joint-fragment-update') {
    return null;
  }

  const currentJointKey = resolveCurrentJointKey(
    currentState.joints,
    patch.previousJointId,
    patch.previousJointName,
  );
  if (!currentJointKey) {
    return null;
  }

  if (
    patch.nextJoint.parentLinkId !== patch.previousParentLinkId ||
    patch.nextJoint.childLinkId !== patch.previousChildLinkId
  ) {
    return null;
  }

  const currentJoint = currentState.joints[currentJointKey];
  return {
    ...currentState,
    joints: {
      ...currentState.joints,
      [currentJointKey]: preserveRuntimeJointMetadata(patch.nextJoint, currentJoint),
    },
    selection: { type: null, id: null },
  };
}

function applyMjcfBodyPatch(
  options: ApplyEditableSourceIncrementalPatchOptions,
): RobotState | null {
  const { currentState, patch } = options;
  if (patch.kind !== 'mjcf-body-subtree-update') {
    return null;
  }

  const currentLinkKeyByName = new Map<string, string>();
  const currentJointKeyByName = new Map<string, string>();

  for (const linkName of patch.stableLinkNames) {
    const currentLinkKey = resolveCurrentLinkKeyByName(currentState.links, linkName);
    if (!currentLinkKey) {
      return null;
    }
    currentLinkKeyByName.set(linkName, currentLinkKey);
  }

  for (const jointName of patch.stableJointNames) {
    const currentJointKey = resolveCurrentJointKeyByName(currentState.joints, jointName);
    if (!currentJointKey) {
      return null;
    }
    currentJointKeyByName.set(jointName, currentJointKey);
  }

  const patchedLinks = { ...currentState.links };
  const patchedJoints = { ...currentState.joints };
  let patchedMaterials: Record<string, RobotMaterialState> | undefined = currentState.materials;

  for (const linkName of patch.stableLinkNames) {
    const currentLinkKey = currentLinkKeyByName.get(linkName);
    const nextLink = patch.nextLinksByName[linkName];
    if (!currentLinkKey || !nextLink) {
      return null;
    }

    const currentLink = currentState.links[currentLinkKey];
    const patchedLink = preserveRuntimeLinkMetadata(nextLink, currentLink);
    patchedLinks[currentLinkKey] = patchedLink;
    patchedMaterials = syncRobotMaterialsForLinkUpdate(patchedMaterials, patchedLink, currentLink);
  }

  for (const jointName of patch.stableJointNames) {
    const currentJointKey = currentJointKeyByName.get(jointName);
    const nextJoint = patch.nextJointsByName[jointName];
    const previousEndpoints = patch.previousJointEndpointsByName[jointName];
    if (!currentJointKey || !nextJoint || !previousEndpoints) {
      return null;
    }

    if (
      nextJoint.parentLinkId !== previousEndpoints.parentLinkId ||
      nextJoint.childLinkId !== previousEndpoints.childLinkId
    ) {
      return null;
    }

    const currentJoint = currentState.joints[currentJointKey];
    patchedJoints[currentJointKey] = preserveRuntimeJointMetadata(nextJoint, currentJoint);
  }

  return {
    ...currentState,
    links: patchedLinks,
    joints: patchedJoints,
    materials: patchedMaterials,
    selection: { type: null, id: null },
  };
}

export function applyEditableSourceIncrementalPatch(
  options: ApplyEditableSourceIncrementalPatchOptions,
): RobotState | null {
  switch (options.patch.kind) {
    case 'urdf-link-fragment-update':
      return applyLinkPatch(options);
    case 'urdf-joint-fragment-update':
      return applyJointPatch(options);
    case 'mjcf-body-subtree-update':
      return applyMjcfBodyPatch(options);
    default:
      return null;
  }
}
