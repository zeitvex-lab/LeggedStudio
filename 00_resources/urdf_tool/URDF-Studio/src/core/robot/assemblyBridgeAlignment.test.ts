import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_LINK, GeometryType, type AssemblyState, type RobotData } from '@/types';

import {
  resolveAssemblyComponentLinkId,
  resolveSuggestedBridgeOriginForVisualContact,
} from './assemblyBridgeAlignment.ts';

function assertNearlyEqual(actual: number, expected: number, message?: string) {
  assert.ok(Math.abs(actual - expected) < 1e-6, message ?? `${actual} !== ${expected}`);
}

function createBoxRobot(
  componentId: string,
  size:
    | number
    | {
        x: number;
        y: number;
        z: number;
      } = 1,
): RobotData {
  const linkId = 'base_link';
  const dimensions =
    typeof size === 'number' ? { x: size, y: size, z: size } : { x: size.x, y: size.y, z: size.z };
  return {
    name: `${componentId}_robot`,
    rootLinkId: linkId,
    links: {
      [linkId]: {
        ...DEFAULT_LINK,
        id: linkId,
        name: 'base_link',
        visual: {
          type: GeometryType.BOX,
          dimensions,
          color: '#ffffff',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.BOX,
          dimensions,
          color: '#ffffff',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
      },
    },
    joints: {},
    materials: {},
    closedLoopConstraints: [],
  };
}

function createAssemblyState(): AssemblyState {
  return {
    name: 'bridge_contact_demo',
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    components: {
      comp_parent: {
        id: 'comp_parent',
        name: 'Parent',
        sourceFile: 'robots/parent.urdf',
        robot: createBoxRobot('comp_parent'),
        transform: {
          position: { x: 0, y: 0, z: 0 },
          rotation: { r: 0, p: 0, y: 0 },
        },
        visible: true,
      },
      comp_child: {
        id: 'comp_child',
        name: 'Child',
        sourceFile: 'robots/child.urdf',
        robot: createBoxRobot('comp_child'),
        transform: {
          position: { x: 4, y: 0, z: 0 },
          rotation: { r: 0, p: 0, y: 0 },
        },
        visible: true,
      },
    },
    bridges: {},
  };
}

test('resolveAssemblyComponentLinkId accepts exact source-local ids only', () => {
  const component = createAssemblyState().components.comp_parent;

  assert.equal(resolveAssemblyComponentLinkId(component, 'base_link'), 'base_link');
  assert.equal(resolveAssemblyComponentLinkId(component, 'comp_parent_base_link'), null);
});

test('resolveSuggestedBridgeOriginForVisualContact keeps the child on its current side while preventing center overlap', () => {
  const assemblyState = createAssemblyState();

  const suggestedOrigin = resolveSuggestedBridgeOriginForVisualContact({
    assemblyState,
    parentComponentId: 'comp_parent',
    parentLinkId: 'base_link',
    childComponentId: 'comp_child',
    childLinkId: 'base_link',
    origin: {
      xyz: { x: 0, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
  });

  assert.ok(suggestedOrigin, 'expected a suggested bridge origin');
  assertNearlyEqual(
    suggestedOrigin.x,
    1.002,
    'visual contact offset should move the child by both half-widths plus a tiny gap',
  );
  assertNearlyEqual(suggestedOrigin.y, 0);
  assertNearlyEqual(suggestedOrigin.z, 0);
});

test('resolveSuggestedBridgeOriginForVisualContact respects the current component approach direction', () => {
  const assemblyState = createAssemblyState();
  assemblyState.components.comp_child.transform = {
    position: { x: -3, y: 0, z: 0 },
    rotation: { r: 0, p: 0, y: 0 },
  };

  const suggestedOrigin = resolveSuggestedBridgeOriginForVisualContact({
    assemblyState,
    parentComponentId: 'comp_parent',
    parentLinkId: 'base_link',
    childComponentId: 'comp_child',
    childLinkId: 'base_link',
    origin: {
      xyz: { x: 0, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
  });

  assert.ok(suggestedOrigin, 'expected a suggested bridge origin');
  assertNearlyEqual(suggestedOrigin.x, -1.002);
  assertNearlyEqual(suggestedOrigin.y, 0);
  assertNearlyEqual(suggestedOrigin.z, 0);
});

test('resolveSuggestedBridgeOriginForVisualContact prefers the parent dominant axis over a diagonal approach', () => {
  const assemblyState = createAssemblyState();
  assemblyState.components.comp_parent.robot = createBoxRobot('comp_parent', {
    x: 2,
    y: 0.4,
    z: 0.4,
  });
  assemblyState.components.comp_child.transform = {
    position: { x: 3, y: 4, z: 0 },
    rotation: { r: 0, p: 0, y: 0 },
  };

  const suggestedOrigin = resolveSuggestedBridgeOriginForVisualContact({
    assemblyState,
    parentComponentId: 'comp_parent',
    parentLinkId: 'base_link',
    childComponentId: 'comp_child',
    childLinkId: 'base_link',
    origin: {
      xyz: { x: 0, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
  });

  assert.ok(suggestedOrigin, 'expected a suggested bridge origin');
  assertNearlyEqual(
    suggestedOrigin.x,
    1.502,
    'dominant-axis attachment should use the parent long-axis face distance',
  );
  assertNearlyEqual(
    suggestedOrigin.y,
    0,
    'dominant-axis attachment should avoid preserving a diagonal center-to-center offset',
  );
  assertNearlyEqual(suggestedOrigin.z, 0);
});

test('resolveSuggestedBridgeOriginForVisualContact logs an error when it falls back without renderable bounds', () => {
  const assemblyState = createAssemblyState();
  assemblyState.components.comp_parent.robot.links.base_link = {
    ...assemblyState.components.comp_parent.robot.links.base_link,
    visual: {
      type: GeometryType.NONE,
      dimensions: { x: 0, y: 0, z: 0 },
      color: '#ffffff',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
    collision: {
      type: GeometryType.NONE,
      dimensions: { x: 0, y: 0, z: 0 },
      color: '#ffffff',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
  };

  const originalConsoleError = console.error;
  const consoleErrors: unknown[][] = [];
  console.error = (...args: unknown[]) => {
    consoleErrors.push(args);
  };

  try {
    const suggestedOrigin = resolveSuggestedBridgeOriginForVisualContact({
      assemblyState,
      parentComponentId: 'comp_parent',
      parentLinkId: 'base_link',
      childComponentId: 'comp_child',
      childLinkId: 'base_link',
      origin: {
        xyz: { x: 0, y: 0, z: 0 },
        rpy: { r: 0, p: 0, y: 0 },
      },
    });

    assert.ok(suggestedOrigin, 'expected a fallback bridge origin');
    assertNearlyEqual(suggestedOrigin.x, 0.12);
    assertNearlyEqual(suggestedOrigin.y, 0);
    assertNearlyEqual(suggestedOrigin.z, 0);
    assert.equal(consoleErrors.length, 1, 'expected exactly one console.error for the fallback');
    assert.match(String(consoleErrors[0]?.[0] ?? ''), /\[AssemblyBridgeAlignment\]/);
  } finally {
    console.error = originalConsoleError;
  }
});
