import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  GeometryType,
  JointType,
  entityRefKey,
  type AssemblyComponent,
  type AssemblyState,
  type AssemblyTransform,
  type EntityRef,
  type RobotData,
} from '@/types';
import {
  generateMujocoXML,
  generateURDF,
  parseMJCF,
  parseURDF,
} from '@/core/parsers';

import { createAssemblyScenePlacement } from './assemblyScenePlacement.ts';
import { createAssemblySceneProjection } from './assemblySceneProjection.ts';
import { resolveAssemblyComponentResourcePath } from './assemblyResourcePaths.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;

function createRobot(name: string, includeTendon = true): RobotData {
  return {
    name,
    rootLinkId: 'base',
    links: {
      base: {
        ...structuredClone(DEFAULT_LINK),
        id: 'base',
        name: 'authored_base',
        mjcfSites: [
          {
            name: 'anchor_internal',
            sourceName: 'anchor',
            type: 'sphere',
          },
        ],
      },
      tip: {
        ...structuredClone(DEFAULT_LINK),
        id: 'tip',
        name: 'authored_tip',
        visual: {
          ...structuredClone(DEFAULT_LINK.visual),
          name: 'wrap_geom',
        },
      },
    },
    joints: {
      hinge: {
        ...structuredClone(DEFAULT_JOINT),
        id: 'hinge',
        name: 'authored_hinge',
        type: JointType.REVOLUTE,
        parentLinkId: 'base',
        childLinkId: 'tip',
      },
    },
    inspectionContext: includeTendon
      ? {
          sourceFormat: 'mjcf',
          mjcf: {
            siteCount: 1,
            tendonCount: 1,
            tendonActuatorCount: 0,
            bodiesWithSites: [
              {
                bodyId: 'base',
                siteCount: 1,
                siteNames: ['anchor_internal'],
              },
            ],
            tendons: [
              {
                name: 'cable',
                type: 'spatial',
                attachmentRefs: ['anchor', 'wrap_geom', 'hinge'],
                attachments: [
                  { type: 'site', ref: 'anchor' },
                  { type: 'geom', ref: 'wrap_geom', sidesite: 'anchor' },
                  { type: 'joint', ref: 'hinge' },
                ],
                actuatorNames: [],
              },
            ],
          },
        }
      : undefined,
  };
}

function createComponent(id: string, robot = createRobot(`${id}_robot`)): AssemblyComponent {
  return {
    id,
    name: id,
    sourceFile: `${id}.xml`,
    robot,
    transform: {
      position: { x: 1, y: 2, z: 3 },
      rotation: { r: 0.1, p: 0.2, y: 0.3 },
    },
    visible: true,
  };
}

function createIdentityTransform(): AssemblyTransform {
  return {
    position: { x: 0, y: 0, z: 0 },
    rotation: { r: 0, p: 0, y: 0 },
  };
}

function reverseLookup(
  projection: ReturnType<typeof createAssemblySceneProjection>,
  ref: EntityRef,
): string | undefined {
  return projection.entityRefKeyToGlobal.get(entityRefKey(ref));
}

function deepFreeze<T>(value: T): T {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) {
    return value;
  }

  Object.freeze(value);
  Object.values(value).forEach(deepFreeze);
  return value;
}

test('single visible component projects directly with canonical two-way mappings', () => {
  const assembly: AssemblyState = {
    name: 'workspace',
    transform: {
      position: { x: 10, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0.5 },
    },
    components: { arm: createComponent('arm') },
    bridges: {},
  };
  const sourceSnapshot = structuredClone(assembly);

  const projection = createAssemblySceneProjection(assembly);

  assert.equal(projection.renderStrategy, 'direct-component');
  assert.equal(projection.robotData.rootLinkId, 'base');
  assert.equal(projection.robotData.links.base?.name, 'authored_base');
  assert.equal(projection.robotData.joints.hinge?.name, 'authored_hinge');
  assert.deepEqual(projection.globalToEntityRef.get('base'), {
    type: 'link',
    componentId: 'arm',
    entityId: 'base',
  });
  assert.equal(
    reverseLookup(projection, { type: 'joint', componentId: 'arm', entityId: 'hinge' }),
    'hinge',
  );
  assert.equal(
    reverseLookup(projection, { type: 'tendon', componentId: 'arm', entityId: 'cable' }),
    'cable',
  );
  assert.equal(projection.robotData.inspectionContext?.mjcf?.tendons[0]?.name, 'cable');
  assert.deepEqual(projection.robotData.inspectionContext?.mjcf?.tendons[0]?.attachmentRefs, [
    'anchor',
    'wrap_geom',
    'hinge',
  ]);
  assert.deepEqual(projection.componentRootTargets.get('arm'), {
    componentId: 'arm',
    rootLinkId: 'base',
    assemblyTransform: assembly.transform,
    componentTransform: assembly.components.arm!.transform,
  });
  assert.notEqual(
    projection.componentRootTargets.get('arm')?.assemblyTransform,
    assembly.transform,
  );
  assert.deepEqual(assembly, sourceSnapshot);
  assert.deepEqual(projection.robotData, assembly.components.arm!.robot);
  assert.notEqual(projection.robotData, assembly.components.arm!.robot);
});

test('direct projection preserves non-entity auxiliary names across source collisions', () => {
  const robot = createRobot('direct-collision');
  robot.links.base!.visual = {
    ...robot.links.base!.visual,
    name: 'base',
    authoredMaterials: [{ name: 'base', color: '#123456' }],
  };
  robot.links.base!.collision = {
    ...robot.links.base!.collision,
    name: 'base',
  };
  robot.links.base!.mjcfSites = [{ name: 'base', sourceName: 'base', type: 'sphere' }];
  robot.materials = { base: { color: '#123456' } };
  robot.closedLoopConstraints = [
    {
      id: 'base',
      type: 'connect',
      linkAId: 'base',
      linkBId: 'tip',
      anchorWorld: { x: 0, y: 0, z: 0 },
      anchorLocalA: { x: 0, y: 0, z: 0 },
      anchorLocalB: { x: 0, y: 0, z: 0 },
    },
  ];
  robot.inspectionContext = {
    sourceFormat: 'mjcf',
    mjcf: {
      siteCount: 1,
      tendonCount: 1,
      tendonActuatorCount: 1,
      bodiesWithSites: [{ bodyId: 'base', siteCount: 1, siteNames: ['base'] }],
      tendons: [
        {
          name: 'base',
          type: 'spatial',
          attachmentRefs: ['base'],
          attachments: [{ type: 'site', ref: 'base' }],
          actuatorNames: ['base'],
        },
      ],
    },
  };
  const workspace: AssemblyState = {
    name: 'direct-collision',
    transform: createIdentityTransform(),
    components: { owner: createComponent('owner', robot) },
    bridges: {},
  };
  const sourceSnapshot = structuredClone(robot);

  const projection = createAssemblySceneProjection(workspace);
  const expectedRobot = structuredClone(sourceSnapshot);
  expectedRobot.inspectionContext!.mjcf!.tendons[0]!.name = 'base__tendon';

  assert.equal(projection.renderStrategy, 'direct-component');
  assert.deepEqual(projection.robotData, expectedRobot);
  assert.equal(
    reverseLookup(projection, { type: 'link', componentId: 'owner', entityId: 'base' }),
    'base',
  );
  assert.equal(
    reverseLookup(projection, { type: 'tendon', componentId: 'owner', entityId: 'base' }),
    'base__tendon',
  );
});

test('multi-component bridge projection namespaces entities and combines tendon mappings', () => {
  const assembly: AssemblyState = {
    name: 'workcell',
    transform: createIdentityTransform(),
    components: {
      arm: createComponent('arm'),
      tool: createComponent('tool'),
    },
    bridges: {
      mount: {
        id: 'mount',
        name: 'mount',
        parentComponentId: 'arm',
        parentLinkId: 'tip',
        childComponentId: 'tool',
        childLinkId: 'base',
        joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'source_mount_joint',
          name: 'source_mount_joint',
          type: JointType.FIXED,
          parentLinkId: 'tip',
          childLinkId: 'base',
        },
      },
    },
  };

  const projection = createAssemblySceneProjection(assembly);

  assert.equal(projection.renderStrategy, 'assembled-scene');
  assert.ok(projection.robotData.links.arm_base);
  assert.ok(projection.robotData.links.tool_base);
  assert.equal(projection.robotData.joints.arm_hinge?.parentLinkId, 'arm_base');
  assert.equal(projection.robotData.links.arm_base?.name, 'arm_base');
  assert.equal(projection.robotData.joints.arm_hinge?.name, 'arm_hinge');
  assert.equal(projection.robotData.joints.mount?.name, 'mount');
  assert.equal(projection.robotData.joints.mount?.childLinkId, 'tool_base');
  assert.deepEqual(projection.globalToEntityRef.get('mount'), {
    type: 'bridge',
    bridgeId: 'mount',
  });
  assert.equal(
    reverseLookup(projection, { type: 'link', componentId: 'tool', entityId: 'tip' }),
    'tool_tip',
  );
  assert.equal(
    reverseLookup(projection, { type: 'tendon', componentId: 'tool', entityId: 'cable' }),
    'tool_cable',
  );
  assert.deepEqual(
    projection.robotData.inspectionContext?.mjcf?.tendons.map((tendon) => tendon.name),
    ['arm_cable', 'tool_cable'],
  );
  assert.deepEqual(projection.robotData.inspectionContext?.mjcf?.tendons[1]?.attachmentRefs, [
    'tool_anchor_internal',
    'tool_wrap_geom',
    'tool_hinge',
  ]);
  assert.equal(projection.robotData.links.tool_tip?.visual.name, 'tool_wrap_geom');
  assert.equal(projection.componentRootTargets.get('arm')?.rootLinkId, 'arm_base');
  assert.equal(projection.componentRootTargets.get('tool')?.rootLinkId, 'tool_base');
});

test('assembled USD projection namespaces identical prepared resource basenames per component', () => {
  const left = createComponent('left', createRobot('left', false));
  const right = createComponent('right', createRobot('right', false));
  left.sourceFile = 'robots/left/model.usd';
  right.sourceFile = 'robots/right/model.usd';
  left.robot.links.base!.visual = {
    ...left.robot.links.base!.visual,
    type: GeometryType.MESH,
    meshPath: 'base_link_visual_0.obj',
    authoredMaterials: [{ texture: 'base_color.png' }],
  };
  right.robot.links.base!.visual = structuredClone(left.robot.links.base!.visual);
  const workspace: AssemblyState = {
    name: 'multi-usd',
    transform: createIdentityTransform(),
    components: { left, right },
    bridges: {},
  };

  const projection = createAssemblySceneProjection(workspace);
  const leftVisual = projection.robotData.links.left_base!.visual;
  const rightVisual = projection.robotData.links.right_base!.visual;

  assert.equal(projection.renderStrategy, 'assembled-scene');
  assert.notEqual(leftVisual.meshPath, rightVisual.meshPath);
  assert.notEqual(
    leftVisual.authoredMaterials?.[0]?.texture,
    rightVisual.authoredMaterials?.[0]?.texture,
  );
  assert.equal(left.robot.links.base!.visual.meshPath, 'base_link_visual_0.obj');
  assert.equal(right.robot.links.base!.visual.meshPath, 'base_link_visual_0.obj');
});

test('assembled resource projection does not prepend a source directory twice', () => {
  const projectedPath = resolveAssemblyComponentResourcePath({
    componentId: 'left',
    sourceFile: 'robots/left/model.urdf',
    resourcePath: 'robots/left/meshes/body.obj',
    renderStrategy: 'assembled-scene',
  });

  assert.equal(
    projectedPath,
    '__workspace__/components/left/robots/left/meshes/body.obj',
  );
  assert.equal(projectedPath.includes('robots/left/robots/left'), false);
});

test('same-source multi-instance projection exports and reparses unique URDF entity names', () => {
  const sharedRobot = createRobot('shared_robot', false);
  const workspace: AssemblyState = {
    name: 'duplicated-workcell',
    transform: createIdentityTransform(),
    components: {
      left: createComponent('left', sharedRobot),
      right: createComponent('right', sharedRobot),
    },
    bridges: {
      mount: {
        id: 'mount',
        name: 'authored_hinge',
        parentComponentId: 'left',
        parentLinkId: 'tip',
        childComponentId: 'right',
        childLinkId: 'base',
        joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'mount',
          name: 'authored_hinge',
          type: JointType.FIXED,
          parentLinkId: 'tip',
          childLinkId: 'base',
        },
      },
    },
  };

  const projection = createAssemblySceneProjection(workspace);
  const generated = generateURDF({
    ...projection.robotData,
    selection: { type: null, id: null },
  });
  const linkNames = Array.from(generated.matchAll(/<link name="([^"]+)"/g), (match) => match[1]!);
  const jointNames = Array.from(generated.matchAll(/<joint name="([^"]+)"/g), (match) => match[1]!);

  assert.equal(linkNames.length, 4);
  assert.equal(new Set(linkNames).size, linkNames.length);
  assert.equal(jointNames.length, 3);
  assert.equal(new Set(jointNames).size, jointNames.length);
  assert.deepEqual(linkNames.sort(), ['left_base', 'left_tip', 'right_base', 'right_tip']);
  assert.deepEqual(jointNames.sort(), ['left_hinge', 'mount', 'right_hinge']);

  const reparsed = parseURDF(generated);
  assert.ok(reparsed);
  assert.equal(Object.keys(reparsed.links).length, 4);
  assert.equal(Object.keys(reparsed.joints).length, 3);
  assert.equal(new Set(Object.values(reparsed.links).map((link) => link.name)).size, 4);
  assert.equal(new Set(Object.values(reparsed.joints).map((joint) => joint.name)).size, 3);
});

test('same-source MJCF sites use projected names that stay aligned with tendon references', () => {
  const sharedRobot = createRobot('shared_robot');
  const workspace: AssemblyState = {
    name: 'duplicated-mjcf',
    transform: createIdentityTransform(),
    components: {
      left: createComponent('left', sharedRobot),
      right: createComponent('right', sharedRobot),
    },
    bridges: {},
  };
  const projection = createAssemblySceneProjection(workspace);
  const placement = createAssemblyScenePlacement(workspace, projection);

  assert.equal(projection.robotData.links.left_base?.mjcfSites?.[0]?.sourceName, undefined);
  assert.equal(projection.robotData.links.right_base?.mjcfSites?.[0]?.sourceName, undefined);
  const tendonSiteRefs = projection.robotData.inspectionContext?.mjcf?.tendons.flatMap(
    (tendon) => tendon.attachments.flatMap((attachment) =>
      attachment.type === 'site' && attachment.ref ? [attachment.ref] : []
    ),
  ) ?? [];
  assert.deepEqual(tendonSiteRefs, ['left_anchor_internal', 'right_anchor_internal']);

  const generated = generateMujocoXML({
    ...placement.robotData,
    selection: { type: null, id: null },
  }, { includeSceneHelpers: false });
  const exportedSiteNames = new Set(
    Array.from(generated.matchAll(/<site\s+[^>]*name="([^"]+)"/g), (match) => match[1]!),
  );
  tendonSiteRefs.forEach((siteRef) => assert.equal(exportedSiteNames.has(siteRef), true));

  const reparsed = parseMJCF(generated);
  assert.ok(reparsed);
  const reparsedSiteNames = new Set(
    Object.values(reparsed.links).flatMap((link) =>
      (link.mjcfSites ?? []).map((site) => site.sourceName ?? site.name)
    ),
  );
  tendonSiteRefs.forEach((siteRef) => assert.equal(reparsedSiteNames.has(siteRef), true));
});

test('component root targets follow runtime rerooting without mutating the source root', () => {
  const assembly: AssemblyState = {
    name: 'rerooted-workcell',
    transform: createIdentityTransform(),
    components: {
      arm: createComponent('arm'),
      tool: createComponent('tool'),
    },
    bridges: {
      mount_at_descendant: {
        id: 'mount_at_descendant',
        name: 'mount_at_descendant',
        parentComponentId: 'arm',
        parentLinkId: 'tip',
        childComponentId: 'tool',
        childLinkId: 'tip',
        joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'source_mount_at_descendant',
          name: 'source_mount_at_descendant',
          type: JointType.FIXED,
          parentLinkId: 'tip',
          childLinkId: 'tip',
        },
      },
    },
  };
  const sourceSnapshot = structuredClone(assembly);
  const projection = createAssemblySceneProjection(assembly);

  assert.equal(projection.robotData.joints.mount_at_descendant?.childLinkId, 'tool_tip');
  assert.equal(projection.componentRootTargets.get('tool')?.rootLinkId, 'tool_tip');
  assert.equal(assembly.components.tool!.robot.rootLinkId, 'base');
  assert.deepEqual(assembly, sourceSnapshot);
});

test('assembled projection resolves underscore collisions without owner inference', () => {
  const createRootOnlyRobot = (rootLinkId: string): RobotData => {
    const authoredName = `authored_${rootLinkId}`;
    return {
      name: rootLinkId,
      rootLinkId,
      links: {
        [rootLinkId]: {
          ...structuredClone(DEFAULT_LINK),
          id: rootLinkId,
          name: authoredName,
        },
      },
      joints: {},
      materials: {
        [authoredName]: { color: rootLinkId === 'b_c' ? '#111111' : '#222222' },
      },
      inspectionContext: {
        sourceFormat: 'mjcf',
        mjcf: {
          siteCount: 0,
          tendonCount: 0,
          tendonActuatorCount: 0,
          bodiesWithSites: [{ bodyId: authoredName, siteCount: 0, siteNames: [] }],
          tendons: [],
        },
      },
    };
  };
  const assembly: AssemblyState = {
    name: 'collision-test',
    transform: createIdentityTransform(),
    components: {
      a: createComponent('a', createRootOnlyRobot('b_c')),
      a_b: createComponent('a_b', createRootOnlyRobot('c')),
    },
    bridges: {},
  };

  const projection = createAssemblySceneProjection(assembly);
  const firstRef: EntityRef = { type: 'link', componentId: 'a', entityId: 'b_c' };
  const secondRef: EntityRef = { type: 'link', componentId: 'a_b', entityId: 'c' };
  const firstGlobalId = reverseLookup(projection, firstRef);
  const secondGlobalId = reverseLookup(projection, secondRef);

  assert.equal(firstGlobalId, 'a_b_c');
  assert.equal(secondGlobalId, 'a_b_c__link');
  assert.notEqual(firstGlobalId, secondGlobalId);
  assert.deepEqual(projection.globalToEntityRef.get(firstGlobalId!), firstRef);
  assert.deepEqual(projection.globalToEntityRef.get(secondGlobalId!), secondRef);
  assert.equal(projection.componentRootTargets.get('a')?.rootLinkId, firstGlobalId);
  assert.equal(projection.componentRootTargets.get('a_b')?.rootLinkId, secondGlobalId);
  assert.equal(projection.robotData.materials?.[firstGlobalId!]?.color, '#111111');
  assert.equal(projection.robotData.materials?.[secondGlobalId!]?.color, '#222222');
  assert.deepEqual(
    projection.robotData.inspectionContext?.mjcf?.bodiesWithSites.map((body) => body.bodyId),
    [firstGlobalId, secondGlobalId],
  );
});

test('direct projection disambiguates cross-kind global ids without losing canonical refs', () => {
  const robot = createRobot('cross-kind');
  robot.rootLinkId = 'shared';
  robot.links = {
    shared: { ...structuredClone(DEFAULT_LINK), id: 'shared', name: 'shared' },
    tip: { ...structuredClone(DEFAULT_LINK), id: 'tip', name: 'tip' },
  };
  robot.joints = {
    shared: {
      ...structuredClone(DEFAULT_JOINT),
      id: 'shared',
      name: 'shared',
      parentLinkId: 'shared',
      childLinkId: 'tip',
    },
  };
  robot.inspectionContext = {
    sourceFormat: 'mjcf',
    mjcf: {
      siteCount: 0,
      tendonCount: 1,
      tendonActuatorCount: 0,
      bodiesWithSites: [],
      tendons: [
        {
          name: 'shared',
          type: 'fixed',
          attachmentRefs: ['shared', 'shared'],
          // Exercise the untyped fallback used by older renderer metadata: the
          // same joint may appear more than once and must stay non-ambiguous.
          attachments: [],
          actuatorNames: [],
        },
      ],
    },
  };
  const assembly: AssemblyState = {
    name: 'cross-kind',
    transform: createIdentityTransform(),
    components: { owner: createComponent('owner', robot) },
    bridges: {},
  };

  const projection = createAssemblySceneProjection(assembly);
  const linkRef: EntityRef = { type: 'link', componentId: 'owner', entityId: 'shared' };
  const jointRef: EntityRef = { type: 'joint', componentId: 'owner', entityId: 'shared' };
  const tendonRef: EntityRef = { type: 'tendon', componentId: 'owner', entityId: 'shared' };

  assert.equal(reverseLookup(projection, linkRef), 'shared');
  assert.equal(reverseLookup(projection, jointRef), 'shared__joint');
  assert.equal(reverseLookup(projection, tendonRef), 'shared__tendon');
  assert.deepEqual(projection.globalToEntityRef.get('shared'), linkRef);
  assert.deepEqual(projection.globalToEntityRef.get('shared__joint'), jointRef);
  assert.deepEqual(projection.globalToEntityRef.get('shared__tendon'), tendonRef);
  assert.ok(projection.robotData.joints.shared__joint);
  assert.equal(projection.robotData.inspectionContext?.mjcf?.tendons[0]?.name, 'shared__tendon');
  assert.deepEqual(projection.robotData.inspectionContext?.mjcf?.tendons[0]?.attachmentRefs, [
    'shared__joint',
    'shared__joint',
  ]);
});

test('bridge ids are explicitly disambiguated from component joint globals', () => {
  const assembly: AssemblyState = {
    name: 'bridge-collision',
    transform: createIdentityTransform(),
    components: {
      arm: createComponent('arm'),
      tool: createComponent('tool'),
    },
    bridges: {
      arm_hinge: {
        id: 'arm_hinge',
        name: 'arm_hinge',
        parentComponentId: 'arm',
        parentLinkId: 'tip',
        childComponentId: 'tool',
        childLinkId: 'base',
        joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'arm_hinge',
          name: 'arm_hinge',
          parentLinkId: 'tip',
          childLinkId: 'base',
        },
      },
    },
  };

  const projection = createAssemblySceneProjection(assembly);
  const componentJointRef: EntityRef = {
    type: 'joint',
    componentId: 'arm',
    entityId: 'hinge',
  };
  const bridgeRef: EntityRef = { type: 'bridge', bridgeId: 'arm_hinge' };

  assert.equal(reverseLookup(projection, componentJointRef), 'arm_hinge');
  assert.equal(reverseLookup(projection, bridgeRef), 'arm_hinge__bridge');
  assert.ok(projection.robotData.joints.arm_hinge);
  assert.ok(projection.robotData.joints.arm_hinge__bridge);
  assert.deepEqual(projection.globalToEntityRef.get('arm_hinge'), componentJointRef);
  assert.deepEqual(projection.globalToEntityRef.get('arm_hinge__bridge'), bridgeRef);
});

test('closed-loop projection ids are collision-safe and keep explicit link references', () => {
  const leftRobot = createRobot('left', false);
  const rightRobot = createRobot('right', false);
  leftRobot.closedLoopConstraints = [
    {
      id: 'b_c',
      type: 'connect',
      linkAId: 'base',
      linkBId: 'tip',
      anchorWorld: { x: 0, y: 0, z: 0 },
      anchorLocalA: { x: 0, y: 0, z: 0 },
      anchorLocalB: { x: 0, y: 0, z: 0 },
    },
  ];
  rightRobot.closedLoopConstraints = [
    {
      ...structuredClone(leftRobot.closedLoopConstraints[0]!),
      id: 'c',
    },
  ];
  const assembly: AssemblyState = {
    name: 'constraint-collision',
    transform: createIdentityTransform(),
    components: {
      a: createComponent('a', leftRobot),
      a_b: createComponent('a_b', rightRobot),
    },
    bridges: {},
  };

  const projection = createAssemblySceneProjection(assembly);

  assert.deepEqual(
    projection.robotData.closedLoopConstraints?.map((constraint) => constraint.id),
    ['a_b_c', 'a_b_c__constraint'],
  );
  assert.deepEqual(
    projection.robotData.closedLoopConstraints?.map((constraint) => [
      constraint.linkAId,
      constraint.linkBId,
    ]),
    [
      ['a_base', 'a_tip'],
      ['a_b_base', 'a_b_tip'],
    ],
  );
});

test('strategy switches preserve canonical mapping semantics and frozen workspace inputs', () => {
  const hiddenTool = createComponent('tool');
  hiddenTool.visible = false;
  const directWorkspace = deepFreeze<AssemblyState>({
    name: 'strategy-switch',
    transform: createIdentityTransform(),
    components: {
      arm: createComponent('arm'),
      tool: hiddenTool,
    },
    bridges: {},
  });
  const directSnapshot = structuredClone(directWorkspace);
  const directProjection = createAssemblySceneProjection(directWorkspace);

  const visibleWorkspace = structuredClone(directWorkspace);
  visibleWorkspace.components.tool!.visible = true;
  const assembledSnapshot = structuredClone(visibleWorkspace);
  const assembledProjection = createAssemblySceneProjection(deepFreeze(visibleWorkspace));
  const ref: EntityRef = { type: 'link', componentId: 'arm', entityId: 'base' };
  const directGlobalId = reverseLookup(directProjection, ref);
  const assembledGlobalId = reverseLookup(assembledProjection, ref);

  assert.equal(directProjection.renderStrategy, 'direct-component');
  assert.equal(assembledProjection.renderStrategy, 'assembled-scene');
  assert.equal(directGlobalId, 'base');
  assert.equal(assembledGlobalId, 'arm_base');
  assert.deepEqual(directProjection.globalToEntityRef.get(directGlobalId!), ref);
  assert.deepEqual(assembledProjection.globalToEntityRef.get(assembledGlobalId!), ref);
  assert.deepEqual(directWorkspace, directSnapshot);
  assert.deepEqual(visibleWorkspace, assembledSnapshot);
});

test('any bridge forces assembled strategy even when exactly one component is visible', () => {
  const hiddenTool = createComponent('tool');
  hiddenTool.visible = false;
  const assembly: AssemblyState = {
    name: 'hidden-bridge',
    transform: createIdentityTransform(),
    components: {
      arm: createComponent('arm'),
      tool: hiddenTool,
    },
    bridges: {
      hidden_mount: {
        id: 'hidden_mount',
        name: 'hidden_mount',
        parentComponentId: 'arm',
        parentLinkId: 'tip',
        childComponentId: 'tool',
        childLinkId: 'base',
        joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'hidden_mount',
          name: 'hidden_mount',
          parentLinkId: 'tip',
          childLinkId: 'base',
        },
      },
    },
  };

  const projection = createAssemblySceneProjection(assembly);

  assert.equal(projection.renderStrategy, 'assembled-scene');
  assert.ok(projection.robotData.links.arm_base);
  assert.equal(projection.robotData.links.tool_base, undefined);
  assert.equal(reverseLookup(projection, { type: 'bridge', bridgeId: 'hidden_mount' }), undefined);
});

test('projection fails fast instead of inventing ids for stale canonical references', () => {
  const robot = createRobot('stale-ref');
  robot.inspectionContext!.mjcf!.tendons[0]!.attachments[0]!.ref = 'missing_site';
  robot.inspectionContext!.mjcf!.tendons[0]!.attachmentRefs[0] = 'missing_site';
  const assembly: AssemblyState = {
    name: 'stale-ref',
    transform: createIdentityTransform(),
    components: {
      arm: createComponent('arm', robot),
      tool: createComponent('tool', createRobot('tool', false)),
    },
    bridges: {},
  };

  assert.throws(
    () => createAssemblySceneProjection(assembly),
    /tendon site attachment "missing_site" does not exist/,
  );
});
