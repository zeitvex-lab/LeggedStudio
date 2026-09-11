import type {
  AssemblyComponent,
  AssemblyState,
  AssemblyTransform,
  BridgeJoint,
  RobotData,
  RobotFile,
} from '@/types';
import { DEFAULT_JOINT, JointType } from '@/types';
import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import {
  buildAssemblyComponentIdentity,
  prepareAssemblyRobotData,
} from '@/core/robot/assemblyComponentPreparation';

interface AutoSeedAssemblyOptions {
  sourceFile?: RobotFile | null;
  availableFiles?: RobotFile[];
  assets?: Record<string, string>;
  allFileContents?: Record<string, string>;
  splitMjcfSceneIncludes?: boolean;
}

interface PreparedAssemblyComponentSeed {
  component: AssemblyComponent;
  displayName: string;
}

function createIdentityAssemblyTransform(): AssemblyTransform {
  return {
    position: { x: 0, y: 0, z: 0 },
    rotation: { r: 0, p: 0, y: 0 },
  };
}

function normalizePath(path: string): string {
  const slashNormalized = path.replace(/\\/g, '/').replace(/\/+/g, '/');
  const hasLeadingSlash = slashNormalized.startsWith('/');
  const parts = slashNormalized.split('/').filter(Boolean);
  const resolved: string[] = [];

  parts.forEach((part) => {
    if (part === '.') {
      return;
    }

    if (part === '..') {
      resolved.pop();
      return;
    }

    resolved.push(part);
  });

  const normalized = resolved.join('/');
  if (!normalized) {
    return hasLeadingSlash ? '/' : '';
  }

  return hasLeadingSlash ? `/${normalized}` : normalized;
}

function getBasePath(path: string): string {
  const normalized = normalizePath(path);
  const parts = normalized.split('/');
  parts.pop();
  return parts.join('/');
}

function resolveMjcfIncludeFile(
  includePath: string,
  sourceFileName: string,
  availableFiles: readonly RobotFile[],
): RobotFile | null {
  const normalizedIncludePath = normalizePath(includePath.trim());
  if (!normalizedIncludePath) {
    return null;
  }

  const byNormalizedPath = new Map(
    availableFiles
      .filter((file) => file.format === 'mjcf')
      .map((file) => [normalizePath(file.name), file] as const),
  );
  const normalizedBasePath = getBasePath(sourceFileName);

  if (normalizedBasePath) {
    const isAbsoluteBase = normalizedBasePath.startsWith('/');
    const baseParts = normalizedBasePath.split('/').filter(Boolean);
    for (let index = baseParts.length; index >= 0; index -= 1) {
      const prefix = baseParts.slice(0, index).join('/');
      const scopedBase = prefix
        ? isAbsoluteBase
          ? `/${prefix}`
          : prefix
        : isAbsoluteBase
          ? '/'
          : '';
      const candidatePath = normalizePath(
        scopedBase ? `${scopedBase}/${normalizedIncludePath}` : normalizedIncludePath,
      );
      const candidate = byNormalizedPath.get(candidatePath);
      if (candidate) {
        return candidate;
      }
    }
  }

  return byNormalizedPath.get(normalizedIncludePath) ?? null;
}

function parseMjcfSceneOnlySource(file: RobotFile): {
  includePaths: string[];
  content: string;
} | null {
  if (file.format !== 'mjcf' || !file.content || typeof DOMParser === 'undefined') {
    return null;
  }

  const doc = new DOMParser().parseFromString(file.content, 'text/xml');
  if (doc.querySelector('parsererror')) {
    return null;
  }

  const mujocoElement = doc.documentElement;
  if (!mujocoElement || mujocoElement.tagName.toLowerCase() !== 'mujoco') {
    return null;
  }

  const includeElements = Array.from(mujocoElement.children).filter(
    (child): child is Element =>
      child.tagName.toLowerCase() === 'include' && Boolean(child.getAttribute('file')?.trim()),
  );
  if (includeElements.length === 0 || typeof XMLSerializer === 'undefined') {
    return null;
  }

  const includePaths = includeElements
    .map((includeElement) => includeElement.getAttribute('file')?.trim())
    .filter((value): value is string => Boolean(value));

  includeElements.forEach((includeElement) => includeElement.remove());

  return {
    includePaths,
    content: new XMLSerializer().serializeToString(doc),
  };
}

function createAssemblyComponentSeed({
  robotData,
  sourceFile,
  existingComponentIds,
  existingComponentNames,
}: {
  robotData: RobotData;
  sourceFile: RobotFile;
  existingComponentIds: Iterable<string>;
  existingComponentNames: Iterable<string>;
}): PreparedAssemblyComponentSeed {
  const { componentId, displayName } = buildAssemblyComponentIdentity({
    fileName: sourceFile.name,
    existingComponentIds,
    existingComponentNames,
  });
  const preparedRobotData = prepareAssemblyRobotData(robotData, {
    sourceFilePath: sourceFile.name,
    sourceFormat: sourceFile.format,
  });
  const componentName = robotData.name || displayName;

  return {
    displayName,
    component: {
      id: componentId,
      name: componentName,
      sourceFile: sourceFile.name,
      robot: preparedRobotData,
      transform: createIdentityAssemblyTransform(),
      visible: true,
    },
  };
}

function createSceneBridge(
  sceneComponent: AssemblyComponent,
  robotComponent: AssemblyComponent,
): BridgeJoint {
  const bridgeId = `bridge_${sceneComponent.id}_to_${robotComponent.id}`;
  const bridgeName = `${sceneComponent.name}_to_${robotComponent.name}`;

  return {
    id: bridgeId,
    name: bridgeName,
    parentComponentId: sceneComponent.id,
    parentLinkId: sceneComponent.robot.rootLinkId,
    childComponentId: robotComponent.id,
    childLinkId: robotComponent.robot.rootLinkId,
    joint: {
      ...DEFAULT_JOINT,
      id: bridgeId,
      name: bridgeName,
      type: JointType.FIXED,
      parentLinkId: sceneComponent.robot.rootLinkId,
      childLinkId: robotComponent.robot.rootLinkId,
      origin: {
        xyz: { x: 0, y: 0, z: 0 },
        rpy: { r: 0, p: 0, y: 0 },
      },
      axis: undefined,
      limit: undefined,
      dynamics: { damping: 0, friction: 0 },
    },
  };
}

function autoSeedMjcfSceneAssembly(
  robotData: RobotData,
  sourceFileName: string,
  options: AutoSeedAssemblyOptions,
): AssemblyState | null {
  const sourceFile =
    options.sourceFile ??
    options.availableFiles?.find((file) => file.name === sourceFileName) ??
    null;
  const availableFiles = options.availableFiles ?? (sourceFile ? [sourceFile] : []);
  if (!sourceFile || sourceFile.format !== 'mjcf') {
    return null;
  }

  const sceneOnlySource = parseMjcfSceneOnlySource(sourceFile);
  if (!sceneOnlySource) {
    return null;
  }

  const includedFiles = sceneOnlySource.includePaths
    .map((includePath) => resolveMjcfIncludeFile(includePath, sourceFile.name, availableFiles))
    .filter((file): file is RobotFile => Boolean(file));
  if (includedFiles.length === 0) {
    return null;
  }

  const sceneOnlyFile: RobotFile = {
    ...sourceFile,
    content: sceneOnlySource.content,
  };
  const sceneAvailableFiles = [
    ...availableFiles.filter((file) => file.name !== sceneOnlyFile.name),
    sceneOnlyFile,
  ];
  const sceneAllFileContents = {
    ...(options.allFileContents ?? {}),
    [sceneOnlyFile.name]: sceneOnlyFile.content,
  };
  const sceneImportResult = resolveRobotFileData(sceneOnlyFile, {
    availableFiles: sceneAvailableFiles,
    assets: options.assets,
    allFileContents: sceneAllFileContents,
  });
  if (sceneImportResult.status !== 'ready') {
    return null;
  }

  const includedRobotSeeds = includedFiles.flatMap((includedFile) => {
    const includedImportResult = resolveRobotFileData(includedFile, {
      availableFiles,
      assets: options.assets,
      allFileContents: options.allFileContents,
    });

    return includedImportResult.status === 'ready'
      ? [{ file: includedFile, robotData: includedImportResult.robotData }]
      : [];
  });
  if (includedRobotSeeds.length === 0) {
    return null;
  }

  const componentSeeds: PreparedAssemblyComponentSeed[] = [];
  const sceneSeed = createAssemblyComponentSeed({
    robotData: sceneImportResult.robotData,
    sourceFile: sceneOnlyFile,
    existingComponentIds: [],
    existingComponentNames: [],
  });
  componentSeeds.push(sceneSeed);

  includedRobotSeeds.forEach((seed) => {
    componentSeeds.push(
      createAssemblyComponentSeed({
        robotData: seed.robotData,
        sourceFile: seed.file,
        existingComponentIds: componentSeeds.map((componentSeed) => componentSeed.component.id),
        existingComponentNames: componentSeeds.flatMap((componentSeed) => [
          componentSeed.displayName,
          componentSeed.component.name,
        ]),
      }),
    );
  });

  const [primaryRobotSeed] = includedRobotSeeds;
  const primaryRobotName = primaryRobotSeed?.robotData.name || robotData.name;
  const sceneComponent = sceneSeed.component;
  const robotComponents = componentSeeds.slice(1).map((componentSeed) => componentSeed.component);
  const bridges = Object.fromEntries(
    robotComponents.map((robotComponent) => {
      const bridge = createSceneBridge(sceneComponent, robotComponent);
      return [bridge.id, bridge];
    }),
  );

  return {
    name: primaryRobotName,
    transform: createIdentityAssemblyTransform(),
    components: Object.fromEntries(
      componentSeeds.map((componentSeed) => [componentSeed.component.id, componentSeed.component]),
    ),
    bridges,
  };
}

/**
 * Wraps a loaded RobotData into a single-component AssemblyState.
 * Used to unify the tree view — every loaded file becomes an assembly with one component.
 */
export function autoSeedAssembly(
  robotData: RobotData,
  sourceFileName: string,
  options: AutoSeedAssemblyOptions = {},
): AssemblyState {
  if (options.splitMjcfSceneIncludes) {
    const sceneAssembly = autoSeedMjcfSceneAssembly(robotData, sourceFileName, options);
    if (sceneAssembly) {
      return sceneAssembly;
    }
  }

  const { componentId, displayName } = buildAssemblyComponentIdentity({
    fileName: sourceFileName,
    existingComponentIds: [],
    existingComponentNames: [],
  });

  const component: AssemblyComponent = {
    id: componentId,
    name: robotData.name || displayName,
    sourceFile: sourceFileName,
    robot: structuredClone(robotData),
    transform: createIdentityAssemblyTransform(),
    visible: true,
  };

  return {
    name: robotData.name || displayName,
    transform: createIdentityAssemblyTransform(),
    components: { [componentId]: component },
    bridges: {},
  };
}
