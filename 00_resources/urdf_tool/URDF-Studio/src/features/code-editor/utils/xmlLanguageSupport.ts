import type {
  SourceCodeDocumentFlavor,
  SourceCodeEditorLanguageId,
  XmlCompletionEntry,
} from '../types';
import {
  getAllUrdfAttributeNames,
  getAllUrdfElementNames,
  getUrdfAttributesForElement,
  getUrdfEnumValuesForAttribute,
  getUrdfRootSchema,
  getUrdfSchemaNodeByType,
  resolveUrdfChildSchemaType,
} from './urdfSchema.ts';

const XACRO_TAGS = [
  'xacro:macro',
  'xacro:property',
  'xacro:include',
  'xacro:arg',
  'xacro:if',
  'xacro:unless',
  'xacro:insert_block',
];

const XACRO_ATTRIBUTES = [
  'name',
  'value',
  'default',
  'params',
  'filename',
  'ns',
];

const SDF_ROOT_TAG = 'sdf';
const SDF_JOINT_TYPES = [
  'revolute',
  'continuous',
  'prismatic',
  'fixed',
  'ball',
  'universal',
  'revolute2',
  'screw',
  'gearbox',
];
const SDF_SENSOR_TYPES = [
  'camera',
  'depth_camera',
  'gpu_lidar',
  'lidar',
  'imu',
  'contact',
  'force_torque',
  'logical_camera',
];
const SDF_LIGHT_TYPES = ['point', 'directional', 'spot'];
const SDF_TAG_CHILDREN_BY_PARENT: Record<string, string[]> = {
  __root__: ['sdf'],
  sdf: ['model', 'world', 'include', 'actor', 'light'],
  world: ['model', 'include', 'light', 'physics', 'scene', 'gravity', 'plugin'],
  model: ['link', 'joint', 'include', 'frame', 'pose', 'plugin', 'static'],
  link: ['inertial', 'visual', 'collision', 'sensor', 'plugin', 'pose', 'gravity', 'self_collide', 'kinematic'],
  joint: ['parent', 'child', 'axis', 'axis2', 'limit', 'dynamics', 'pose'],
  visual: ['geometry', 'material', 'pose'],
  collision: ['geometry', 'surface', 'pose'],
  geometry: ['box', 'sphere', 'cylinder', 'capsule', 'plane', 'mesh', 'ellipsoid', 'heightmap'],
  axis: ['xyz', 'limit', 'dynamics'],
  axis2: ['xyz', 'limit', 'dynamics'],
};
const SDF_ATTRIBUTES_BY_TAG: Record<string, string[]> = {
  sdf: ['version'],
  model: ['name'],
  world: ['name'],
  link: ['name'],
  joint: ['name', 'type'],
  sensor: ['name', 'type'],
  light: ['name', 'type'],
  plugin: ['name', 'filename'],
  include: ['uri'],
  mesh: ['uri', 'scale'],
  box: ['size'],
  sphere: ['radius'],
  cylinder: ['radius', 'length'],
  capsule: ['radius', 'length'],
  plane: ['normal', 'size'],
  ellipsoid: ['radii'],
  heightmap: ['uri', 'size', 'pos'],
};
const SDF_ATTRIBUTE_VALUE_ENUMS: Record<string, Record<string, string[]>> = {
  joint: { type: SDF_JOINT_TYPES },
  sensor: { type: SDF_SENSOR_TYPES },
  light: { type: SDF_LIGHT_TYPES },
};

const MJCF_ROOT_TAG = 'mujoco';
const MJCF_JOINT_TYPES = ['hinge', 'slide', 'ball', 'free'];
const MJCF_GEOM_TYPES = ['plane', 'hfield', 'sphere', 'capsule', 'ellipsoid', 'cylinder', 'box', 'mesh', 'sdf'];
const MJCF_BOOLEAN_LIKE = ['true', 'false', 'auto'];
const MJCF_TAG_CHILDREN_BY_PARENT: Record<string, string[]> = {
  __root__: ['mujoco'],
  mujoco: [
    'compiler',
    'option',
    'size',
    'statistic',
    'default',
    'custom',
    'asset',
    'worldbody',
    'contact',
    'equality',
    'tendon',
    'actuator',
    'sensor',
    'keyframe',
    'visual',
    'extension',
  ],
  worldbody: ['frame', 'body', 'geom', 'joint', 'freejoint', 'site', 'camera', 'light'],
  body: ['frame', 'body', 'geom', 'joint', 'freejoint', 'site', 'camera', 'light', 'inertial'],
  asset: ['mesh', 'texture', 'material', 'hfield', 'skin'],
  actuator: ['motor', 'position', 'velocity', 'intvelocity', 'general', 'damper', 'muscle', 'adhesion'],
  default: ['default', 'joint', 'geom', 'site', 'tendon', 'motor', 'position', 'general', 'damper', 'muscle'],
};
const MJCF_ATTRIBUTES_BY_TAG: Record<string, string[]> = {
  mujoco: ['model'],
  compiler: ['angle', 'autolimits', 'meshdir', 'texturedir', 'assetdir', 'inertiafromgeom', 'eulerseq'],
  option: ['timestep', 'gravity', 'integrator'],
  body: ['name', 'pos', 'quat', 'euler'],
  joint: ['name', 'type', 'axis', 'pos', 'range', 'limited', 'damping', 'stiffness', 'armature', 'frictionloss'],
  geom: ['name', 'type', 'size', 'pos', 'quat', 'rgba', 'density', 'mass', 'material', 'mesh', 'friction'],
  site: ['name', 'pos', 'quat', 'size', 'type', 'rgba'],
  frame: ['name', 'pos', 'quat', 'euler', 'axis', 'xyaxes', 'zaxis'],
  motor: ['name', 'joint', 'gear', 'ctrlrange', 'ctrllimited'],
  position: ['name', 'joint', 'kp', 'ctrlrange', 'ctrllimited'],
  velocity: ['name', 'joint', 'kv', 'ctrlrange', 'ctrllimited'],
  general: ['name', 'joint', 'class', 'tendon', 'gear', 'ctrlrange', 'forcerange', 'limited', 'biastype', 'gainprm'],
  damper: ['name', 'joint', 'class', 'tendon', 'biastype', 'tendons'],
  muscle: ['name', 'joint', 'tendon', 'gear', 'kp', 'ap'],
  adhesion: ['name', 'tendon', 'tendonpos'],
  tendon: ['name', 'class', 'stiffness', 'width', 'rgba', 'group', 'site', 'geom', 'sidesite', 'springlength'],
  contact: ['name', 'group', 'condim', 'gap', 'margin', 'mode'],
  equality: ['name', 'damping', 'solref', 'solimp', 'tolerance'],
  sensor: ['name', 'type', 'site', 'objtype', 'objname', 'point1', 'point2'],
  keyframe: ['name', 'time', 'duration'],
  visual: ['name', 'objtype', 'objname', 'rgba'],
  extension: ['class', 'filename'],
  mesh: ['name', 'file', 'scale'],
  material: ['name', 'rgba', 'texture'],
  texture: ['name', 'type', 'file', 'builtin'],
};
const MJCF_ATTRIBUTE_VALUE_ENUMS: Record<string, Record<string, string[]>> = {
  compiler: {
    angle: ['degree', 'radian'],
    autolimits: MJCF_BOOLEAN_LIKE,
  },
  joint: {
    type: MJCF_JOINT_TYPES,
    limited: MJCF_BOOLEAN_LIKE,
  },
  geom: {
    type: MJCF_GEOM_TYPES,
  },
  motor: {
    ctrllimited: MJCF_BOOLEAN_LIKE,
  },
  position: {
    ctrllimited: MJCF_BOOLEAN_LIKE,
  },
  velocity: {
    ctrllimited: MJCF_BOOLEAN_LIKE,
  },
  texture: {
    type: ['2d', 'cube', 'skybox'],
    builtin: ['none', 'flat', 'checker', 'gradient'],
  },
};
const MJCF_JOINT_REFERENCE_TAGS = new Set([
  'motor',
  'position',
  'velocity',
  'intvelocity',
  'general',
  'damper',
]);

const URDF_SNIPPETS: XmlCompletionEntry[] = [
  {
    label: 'link-snippet',
    kind: 'snippet',
    insertText:
      '<link name="${1:link_name}">\n\t<visual>\n\t\t<origin xyz="${2:0 0 0}" rpy="${3:0 0 0}"/>\n\t\t<geometry>\n\t\t\t<box size="${4:0.1 0.1 0.1}"/>\n\t\t</geometry>\n\t</visual>\n</link>',
    documentation: 'Basic URDF link structure',
    insertAsSnippet: true,
  },
  {
    label: 'joint-snippet',
    kind: 'snippet',
    insertText:
      '<joint name="${1:joint_name}" type="${2:revolute}">\n\t<parent link="${3:parent_link}"/>\n\t<child link="${4:child_link}"/>\n\t<origin xyz="${5:0 0 0}" rpy="${6:0 0 0}"/>\n\t<axis xyz="${7:0 0 1}"/>\n\t<limit lower="${8:-1.57}" upper="${9:1.57}" effort="${10:100}" velocity="${11:1}"/>\n</joint>',
    documentation: 'Basic URDF joint structure',
    insertAsSnippet: true,
  },
];

const XACRO_SNIPPETS: XmlCompletionEntry[] = [
  {
    label: 'macro-snippet',
    kind: 'snippet',
    insertText:
      '<xacro:macro name="${1:macro_name}" params="${2:param}">\n\t${3}\n</xacro:macro>',
    documentation: 'Define a reusable Xacro macro',
    insertAsSnippet: true,
  },
  {
    label: 'property-snippet',
    kind: 'snippet',
    insertText: '<xacro:property name="${1:property_name}" value="${2:value}" />',
    documentation: 'Define a reusable Xacro property',
    insertAsSnippet: true,
  },
  {
    label: 'include-snippet',
    kind: 'snippet',
    insertText: '<xacro:include filename="${1:$(find package)/urdf/file.xacro}" />',
    documentation: 'Include another Xacro file',
    insertAsSnippet: true,
  },
];

const SDF_SNIPPETS: XmlCompletionEntry[] = [
  {
    label: 'sdf-model-snippet',
    kind: 'snippet',
    insertText:
      '<sdf version="${1:1.10}">\n\t<model name="${2:robot_model}">\n\t\t<link name="${3:base_link}"/>\n\t</model>\n</sdf>',
    documentation: 'Minimal SDF model scaffold',
    insertAsSnippet: true,
  },
  {
    label: 'sdf-joint-snippet',
    kind: 'snippet',
    insertText:
      '<joint name="${1:joint_name}" type="${2:revolute}">\n\t<parent>${3:parent_link}</parent>\n\t<child>${4:child_link}</child>\n\t<axis>\n\t\t<xyz>${5:0 0 1}</xyz>\n\t</axis>\n</joint>',
    documentation: 'SDF joint scaffold with parent/child and axis',
    insertAsSnippet: true,
  },
];

const MJCF_SNIPPETS: XmlCompletionEntry[] = [
  {
    label: 'mjcf-model-snippet',
    kind: 'snippet',
    insertText:
      '<mujoco model="${1:robot_model}">\n\t<worldbody>\n\t\t<body name="${2:base}" pos="${3:0 0 0}">\n\t\t\t<geom type="${4:box}" size="${5:0.1 0.1 0.1}"/>\n\t\t</body>\n\t</worldbody>\n</mujoco>',
    documentation: 'Minimal MJCF model scaffold',
    insertAsSnippet: true,
  },
  {
    label: 'mjcf-hinge-joint-snippet',
    kind: 'snippet',
    insertText:
      '<joint name="${1:joint_name}" type="${2:hinge}" axis="${3:0 0 1}" range="${4:-1.57 1.57}" limited="${5:true}"/>',
    documentation: 'MJCF hinge joint scaffold',
    insertAsSnippet: true,
  },
];

const buildKeywordEntries = (
  labels: string[],
  kind: XmlCompletionEntry['kind'],
): XmlCompletionEntry[] => labels.map((label) => ({ label, kind, insertText: label }));

const uniqueSorted = <T>(values: T[]): T[] => Array.from(new Set(values)).sort();
const flattenUniqueValues = (mapping: Record<string, string[]>): string[] => uniqueSorted(
  Object.entries(mapping)
    .flatMap(([parent, children]) => (parent === '__root__' ? children : [parent, ...children])),
);
const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const parseAttributeEntries = (source: string): Array<{ name: string; value: string }> => {
  const entries: Array<{ name: string; value: string }> = [];
  const attributePattern = /([A-Za-z_:][\w:.-]*)\s*=\s*["']([^"']*)["']/g;
  let match: RegExpExecArray | null = attributePattern.exec(source);

  while (match) {
    entries.push({
      name: match[1],
      value: match[2],
    });
    match = attributePattern.exec(source);
  }

  return entries;
};

const getElementAttributeValues = (
  textBeforeCursor: string,
  elementName: string,
  attributeName: string,
): string[] => {
  const elementPattern = new RegExp(`<${escapeRegExp(elementName)}\\b([^>]*)>`, 'gi');
  const values: string[] = [];
  let match: RegExpExecArray | null = elementPattern.exec(textBeforeCursor);

  while (match) {
    const attributes = parseAttributeEntries(match[1]);
    const found = attributes.find((attribute) => attribute.name === attributeName)?.value;
    if (found && found.trim().length > 0) {
      values.push(found.trim());
    }
    match = elementPattern.exec(textBeforeCursor);
  }

  return uniqueSorted(values);
};

const getXacroMacroDefinitions = (textBeforeCursor: string): Map<string, string[]> => {
  const definitions = new Map<string, string[]>();
  const macroPattern = /<xacro:macro\b([^>]*)>/gi;
  let match: RegExpExecArray | null = macroPattern.exec(textBeforeCursor);

  while (match) {
    const attributes = parseAttributeEntries(match[1]);
    const macroName = attributes.find((attribute) => attribute.name === 'name')?.value?.trim();
    if (!macroName) {
      match = macroPattern.exec(textBeforeCursor);
      continue;
    }

    const paramsRaw = attributes.find((attribute) => attribute.name === 'params')?.value || '';
    const params = uniqueSorted(
      paramsRaw
        .split(/\s+/)
        .map((token) => token.trim())
        .filter((token) => token.length > 0)
        .map((token) => token.replace(/^\*/, '').split(/:=|=/)[0]?.trim() || '')
        .filter((token) => token.length > 0),
    );

    definitions.set(macroName, params);
    match = macroPattern.exec(textBeforeCursor);
  }

  return definitions;
};

const mergeCompletionEntries = (...groups: XmlCompletionEntry[][]): XmlCompletionEntry[] => {
  const merged = new Map<string, XmlCompletionEntry>();
  groups.forEach((entries) => {
    entries.forEach((entry) => {
      const key = `${entry.kind}|${entry.label}|${entry.insertText}`;
      if (!merged.has(key)) {
        merged.set(key, entry);
      }
    });
  });

  return Array.from(merged.values());
};

const EMPTY_ENTRIES: XmlCompletionEntry[] = [];
const URDF_ROOT_TYPE_NAME = getUrdfRootSchema().typeName;
const ROOT_TAG_ENTRIES = buildKeywordEntries(['robot'], 'tag');
const URDF_TAG_ENTRIES = buildKeywordEntries(getAllUrdfElementNames(), 'tag');
const URDF_ATTRIBUTE_ENTRIES = buildKeywordEntries(getAllUrdfAttributeNames(), 'attribute');
const XACRO_TAG_ENTRIES = buildKeywordEntries(XACRO_TAGS, 'tag');
const XACRO_ATTRIBUTE_ENTRIES = buildKeywordEntries(XACRO_ATTRIBUTES, 'attribute');
const SDF_TAG_ENTRIES = buildKeywordEntries(flattenUniqueValues(SDF_TAG_CHILDREN_BY_PARENT), 'tag');
const SDF_ATTRIBUTE_ENTRIES = buildKeywordEntries(flattenUniqueValues(SDF_ATTRIBUTES_BY_TAG), 'attribute');
const MJCF_TAG_ENTRIES = buildKeywordEntries(flattenUniqueValues(MJCF_TAG_CHILDREN_BY_PARENT), 'tag');
const MJCF_ATTRIBUTE_ENTRIES = buildKeywordEntries(flattenUniqueValues(MJCF_ATTRIBUTES_BY_TAG), 'attribute');
const SDF_ROOT_TAG_ENTRIES = buildKeywordEntries([SDF_ROOT_TAG], 'tag');
const MJCF_ROOT_TAG_ENTRIES = buildKeywordEntries([MJCF_ROOT_TAG], 'tag');
const scopedAttributeEntriesCache = new Map<string, XmlCompletionEntry[]>();
const scopedAttributeValueEntriesCache = new Map<string, XmlCompletionEntry[]>();
const scopedTagEntriesCache = new Map<string, XmlCompletionEntry[]>();

const XML_TAG_CONTEXT_PATTERN = /<\/?[\w:.-]*$/i;
const XML_OPENING_TAG_CONTEXT_PATTERN = /<[\w:.-]*$/i;
const XML_CLOSING_TAG_CONTEXT_PATTERN = /<\/[\w:.-]*$/i;
const XML_ATTRIBUTE_CONTEXT_PATTERN = /<[\w:.-]+(?:\s+[\w:.-]+(?:=(?:"[^"]*"|'[^']*'))?)*\s+[\w:.-]*$/i;
const XML_ATTRIBUTE_VALUE_CONTEXT_PATTERN = /<([\w:.-]+)\b[^>]*\b([\w:.-]+)\s*=\s*["'][^"']*$/i;
const XML_OPEN_TAG_NAME_CONTEXT_PATTERN = /<([\w:.-]+)(?=[^<>]*$)/i;

interface ParsedXmlElement {
  elementName: string;
  schemaTypeName: string | null;
}

type XmlTagScope =
  | { kind: 'root' }
  | { kind: 'known'; schemaTypeName: string }
  | { kind: 'unknown' };

const URDF_TAG_ENTRIES_WITH_SNIPPETS = [...URDF_TAG_ENTRIES, ...URDF_SNIPPETS];
const XACRO_TAG_ENTRIES_WITH_SNIPPETS = [
  ...URDF_TAG_ENTRIES,
  ...XACRO_TAG_ENTRIES,
  ...URDF_SNIPPETS,
  ...XACRO_SNIPPETS,
];
const XACRO_ROOT_TAG_ENTRIES = [...ROOT_TAG_ENTRIES, ...XACRO_TAG_ENTRIES, ...XACRO_SNIPPETS];
const SDF_TAG_ENTRIES_WITH_SNIPPETS = [...SDF_TAG_ENTRIES, ...SDF_SNIPPETS];
const MJCF_TAG_ENTRIES_WITH_SNIPPETS = [...MJCF_TAG_ENTRIES, ...MJCF_SNIPPETS];

const getUrdfSnippetEntriesForChildTags = (childTagNames: string[]): XmlCompletionEntry[] => {
  const entries: XmlCompletionEntry[] = [];

  if (childTagNames.includes('link')) {
    entries.push(URDF_SNIPPETS[0]);
  }

  if (childTagNames.includes('joint')) {
    entries.push(URDF_SNIPPETS[1]);
  }

  return entries;
};

const getUrdfLikeFallbackTagEntries = (
  documentFlavor: SourceCodeDocumentFlavor,
): XmlCompletionEntry[] => (
  documentFlavor === 'xacro' ? XACRO_TAG_ENTRIES_WITH_SNIPPETS : URDF_TAG_ENTRIES_WITH_SNIPPETS
);

const getUrdfLikeRootTagEntries = (
  documentFlavor: SourceCodeDocumentFlavor,
): XmlCompletionEntry[] => (
  documentFlavor === 'xacro' ? XACRO_ROOT_TAG_ENTRIES : ROOT_TAG_ENTRIES
);

const getScopedTagEntries = (
  documentFlavor: SourceCodeDocumentFlavor,
  scope: XmlTagScope,
): XmlCompletionEntry[] => {
  const cacheKey = scope.kind === 'known'
    ? `${documentFlavor}:schema:${scope.schemaTypeName}`
    : `${documentFlavor}:${scope.kind}`;
  const cached = scopedTagEntriesCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  let entries: XmlCompletionEntry[];

  if (scope.kind === 'root') {
    entries = getUrdfLikeRootTagEntries(documentFlavor);
  } else if (scope.kind === 'unknown') {
    entries = getUrdfLikeFallbackTagEntries(documentFlavor);
  } else {
    const schemaNode = getUrdfSchemaNodeByType(scope.schemaTypeName);
    if (!schemaNode || schemaNode.allowAnyChildren) {
      entries = getUrdfLikeFallbackTagEntries(documentFlavor);
    } else {
      const childTagNames = uniqueSorted(schemaNode.children.map((child) => child.name));
      const tagEntries = buildKeywordEntries(childTagNames, 'tag');
      const urdfSnippetEntries = getUrdfSnippetEntriesForChildTags(childTagNames);

      entries = documentFlavor === 'xacro'
        ? [...tagEntries, ...XACRO_TAG_ENTRIES, ...urdfSnippetEntries, ...XACRO_SNIPPETS]
        : [...tagEntries, ...urdfSnippetEntries];
    }
  }

  scopedTagEntriesCache.set(cacheKey, entries);
  return entries;
};

const getSdfSnippetEntriesForChildTags = (childTagNames: string[]): XmlCompletionEntry[] => {
  const entries: XmlCompletionEntry[] = [];

  if (childTagNames.includes('model')) {
    entries.push(SDF_SNIPPETS[0]);
  }

  if (childTagNames.includes('joint')) {
    entries.push(SDF_SNIPPETS[1]);
  }

  return entries;
};

const getMjcfSnippetEntriesForChildTags = (childTagNames: string[]): XmlCompletionEntry[] => {
  const entries: XmlCompletionEntry[] = [];

  if (childTagNames.includes('mujoco')) {
    entries.push(MJCF_SNIPPETS[0]);
  }

  if (childTagNames.includes('joint')) {
    entries.push(MJCF_SNIPPETS[1]);
  }

  return entries;
};

const getDictionaryTagEntries = (
  cacheKey: string,
  rootEntries: XmlCompletionEntry[],
  fallbackEntries: XmlCompletionEntry[],
  parentElementName: string | null,
  childrenByParent: Record<string, string[]>,
  getSnippetEntriesForChildTags: (childTagNames: string[]) => XmlCompletionEntry[],
): XmlCompletionEntry[] => {
  const cached = scopedTagEntriesCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  let entries: XmlCompletionEntry[] = fallbackEntries;

  if (!parentElementName) {
    entries = rootEntries;
  } else {
    const childTagNames = uniqueSorted(childrenByParent[parentElementName] || []);
    if (childTagNames.length > 0) {
      entries = [
        ...buildKeywordEntries(childTagNames, 'tag'),
        ...getSnippetEntriesForChildTags(childTagNames),
      ];
    }
  }

  scopedTagEntriesCache.set(cacheKey, entries);
  return entries;
};

const findTagEnd = (text: string, startIndex: number): number => {
  let quoteCharacter: '"' | '\'' | null = null;

  for (let index = startIndex; index < text.length; index += 1) {
    const character = text[index];

    if (quoteCharacter) {
      if (character === quoteCharacter) {
        quoteCharacter = null;
      }
      continue;
    }

    if (character === '"' || character === '\'') {
      quoteCharacter = character;
      continue;
    }

    if (character === '>') {
      return index;
    }
  }

  return -1;
};

const readTagName = (text: string, startIndex: number): {
  tagName: string | null;
  nextIndex: number;
} => {
  let index = startIndex;

  while (index < text.length && /\s/.test(text[index])) {
    index += 1;
  }

  const nameStart = index;
  while (index < text.length && /[\w:.-]/.test(text[index])) {
    index += 1;
  }

  if (index === nameStart) {
    return { tagName: null, nextIndex: index };
  }

  return { tagName: text.slice(nameStart, index), nextIndex: index };
};

const isSelfClosingTag = (text: string, tagStartIndex: number, tagEndIndex: number): boolean => {
  let index = tagEndIndex - 1;

  while (index > tagStartIndex && /\s/.test(text[index])) {
    index -= 1;
  }

  return text[index] === '/';
};

const resolveChildSchemaTypeFromStack = (
  stack: ParsedXmlElement[],
  childElementName: string,
): string | null => {
  if (stack.length === 0) {
    return childElementName === 'robot' ? URDF_ROOT_TYPE_NAME : null;
  }

  const parentSchemaTypeName = stack[stack.length - 1]?.schemaTypeName;
  if (!parentSchemaTypeName) {
    return null;
  }

  return resolveUrdfChildSchemaType(parentSchemaTypeName, childElementName);
};

const parseXmlElementStack = (textBeforeCursor: string): ParsedXmlElement[] => {
  const stack: ParsedXmlElement[] = [];
  let index = 0;

  while (index < textBeforeCursor.length) {
    if (textBeforeCursor[index] !== '<') {
      index += 1;
      continue;
    }

    if (textBeforeCursor.startsWith('<!--', index)) {
      const commentEnd = textBeforeCursor.indexOf('-->', index + 4);
      if (commentEnd === -1) {
        break;
      }
      index = commentEnd + 3;
      continue;
    }

    if (textBeforeCursor.startsWith('<![CDATA[', index)) {
      const cdataEnd = textBeforeCursor.indexOf(']]>', index + 9);
      if (cdataEnd === -1) {
        break;
      }
      index = cdataEnd + 3;
      continue;
    }

    if (textBeforeCursor.startsWith('<?', index)) {
      const declarationEnd = textBeforeCursor.indexOf('?>', index + 2);
      if (declarationEnd === -1) {
        break;
      }
      index = declarationEnd + 2;
      continue;
    }

    if (textBeforeCursor.startsWith('</', index)) {
      const { tagName, nextIndex } = readTagName(textBeforeCursor, index + 2);
      if (!tagName) {
        index += 1;
        continue;
      }

      const tagEnd = findTagEnd(textBeforeCursor, nextIndex);
      if (tagEnd === -1) {
        break;
      }

      for (let stackIndex = stack.length - 1; stackIndex >= 0; stackIndex -= 1) {
        if (stack[stackIndex].elementName === tagName) {
          stack.length = stackIndex;
          break;
        }
      }

      index = tagEnd + 1;
      continue;
    }

    if (textBeforeCursor.startsWith('<!', index)) {
      const specialTagEnd = findTagEnd(textBeforeCursor, index + 2);
      if (specialTagEnd === -1) {
        break;
      }
      index = specialTagEnd + 1;
      continue;
    }

    const { tagName, nextIndex } = readTagName(textBeforeCursor, index + 1);
    if (!tagName) {
      index += 1;
      continue;
    }

    const tagEnd = findTagEnd(textBeforeCursor, nextIndex);
    if (tagEnd === -1) {
      break;
    }

    if (!isSelfClosingTag(textBeforeCursor, index, tagEnd)) {
      stack.push({
        elementName: tagName,
        schemaTypeName: resolveChildSchemaTypeFromStack(stack, tagName),
      });
    }

    index = tagEnd + 1;
  }

  return stack;
};

const getTagScope = (textBeforeCursor: string): XmlTagScope => {
  const stack = parseXmlElementStack(textBeforeCursor);
  const currentParent = stack[stack.length - 1];

  if (!currentParent) {
    return { kind: 'root' };
  }

  if (!currentParent.schemaTypeName) {
    return { kind: 'unknown' };
  }

  return { kind: 'known', schemaTypeName: currentParent.schemaTypeName };
};

const getCurrentParentElementName = (textBeforeCursor: string): string | null => {
  const stack = parseXmlElementStack(textBeforeCursor);
  return stack[stack.length - 1]?.elementName || null;
};

const getSdfScopedTagEntries = (textBeforeCursor: string): XmlCompletionEntry[] => {
  const parentElementName = getCurrentParentElementName(textBeforeCursor);
  const cacheKey = parentElementName ? `sdf:parent:${parentElementName}` : 'sdf:root';
  return getDictionaryTagEntries(
    cacheKey,
    SDF_ROOT_TAG_ENTRIES,
    SDF_TAG_ENTRIES_WITH_SNIPPETS,
    parentElementName,
    SDF_TAG_CHILDREN_BY_PARENT,
    getSdfSnippetEntriesForChildTags,
  );
};

const getMjcfScopedTagEntries = (textBeforeCursor: string): XmlCompletionEntry[] => {
  const parentElementName = getCurrentParentElementName(textBeforeCursor);
  const cacheKey = parentElementName ? `mjcf:parent:${parentElementName}` : 'mjcf:root';
  return getDictionaryTagEntries(
    cacheKey,
    MJCF_ROOT_TAG_ENTRIES,
    MJCF_TAG_ENTRIES_WITH_SNIPPETS,
    parentElementName,
    MJCF_TAG_CHILDREN_BY_PARENT,
    getMjcfSnippetEntriesForChildTags,
  );
};

const getScopedAttributeEntries = (
  documentFlavor: SourceCodeDocumentFlavor,
  elementName: string | null,
  textBeforeCursor: string,
): XmlCompletionEntry[] => {
  const cacheKey = `${documentFlavor}:${elementName || '*'}`;
  const shouldBypassCache = documentFlavor === 'xacro'
    && Boolean(elementName && elementName.startsWith('xacro:') && !XACRO_TAGS.includes(elementName));

  if (!shouldBypassCache) {
    const cached = scopedAttributeEntriesCache.get(cacheKey);
    if (cached) {
      return cached;
    }
  }

  let entries: XmlCompletionEntry[] = EMPTY_ENTRIES;

  if (documentFlavor === 'urdf' || documentFlavor === 'xacro') {
    const urdfAttributeEntries = elementName
      ? buildKeywordEntries(
          getUrdfAttributesForElement(elementName).map((attribute) => attribute.name),
          'attribute',
        )
      : URDF_ATTRIBUTE_ENTRIES;

    entries = documentFlavor === 'xacro'
      ? [...urdfAttributeEntries, ...XACRO_ATTRIBUTE_ENTRIES]
      : urdfAttributeEntries;

    if (
      documentFlavor === 'xacro'
      && elementName
      && elementName.startsWith('xacro:')
      && !XACRO_TAGS.includes(elementName)
    ) {
      const macroName = elementName.slice('xacro:'.length);
      const macroDefinitions = getXacroMacroDefinitions(textBeforeCursor);
      const macroParams = macroDefinitions.get(macroName) || [];
      const macroParamEntries = buildKeywordEntries(macroParams, 'attribute');
      entries = mergeCompletionEntries(macroParamEntries, entries);
    }
  } else if (documentFlavor === 'sdf') {
    entries = elementName
      ? buildKeywordEntries(SDF_ATTRIBUTES_BY_TAG[elementName] || [], 'attribute')
      : SDF_ATTRIBUTE_ENTRIES;
  } else if (documentFlavor === 'mjcf' || documentFlavor === 'equivalent-mjcf') {
    entries = elementName
      ? buildKeywordEntries(MJCF_ATTRIBUTES_BY_TAG[elementName] || [], 'attribute')
      : MJCF_ATTRIBUTE_ENTRIES;
  }

  if (!shouldBypassCache) {
    scopedAttributeEntriesCache.set(cacheKey, entries);
  }

  return entries;
};

const getScopedAttributeValueEntries = (
  documentFlavor: SourceCodeDocumentFlavor,
  elementName: string,
  attributeName: string,
  textBeforeCursor: string,
): XmlCompletionEntry[] => {
  if (
    (documentFlavor === 'urdf' || documentFlavor === 'xacro')
    && attributeName === 'link'
    && (elementName === 'parent' || elementName === 'child')
  ) {
    return buildKeywordEntries(getElementAttributeValues(textBeforeCursor, 'link', 'name'), 'value');
  }

  if (
    (documentFlavor === 'mjcf' || documentFlavor === 'equivalent-mjcf')
    && attributeName === 'joint'
    && MJCF_JOINT_REFERENCE_TAGS.has(elementName)
  ) {
    return buildKeywordEntries(getElementAttributeValues(textBeforeCursor, 'joint', 'name'), 'value');
  }

  if (
    (documentFlavor === 'mjcf' || documentFlavor === 'equivalent-mjcf')
    && elementName === 'geom'
    && attributeName === 'mesh'
  ) {
    return buildKeywordEntries(getElementAttributeValues(textBeforeCursor, 'mesh', 'name'), 'value');
  }

  if (
    (documentFlavor === 'mjcf' || documentFlavor === 'equivalent-mjcf')
    && elementName === 'geom'
    && attributeName === 'material'
  ) {
    return buildKeywordEntries(getElementAttributeValues(textBeforeCursor, 'material', 'name'), 'value');
  }

  const cacheKey = `${documentFlavor}:${elementName}:${attributeName}`;
  const cached = scopedAttributeValueEntriesCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  let values: string[] = [];

  if (documentFlavor === 'urdf' || documentFlavor === 'xacro') {
    values = getUrdfEnumValuesForAttribute(elementName, attributeName);
  } else if (documentFlavor === 'sdf') {
    values = SDF_ATTRIBUTE_VALUE_ENUMS[elementName]?.[attributeName] || [];
  } else if (documentFlavor === 'mjcf' || documentFlavor === 'equivalent-mjcf') {
    values = MJCF_ATTRIBUTE_VALUE_ENUMS[elementName]?.[attributeName] || [];
  }

  const entries = buildKeywordEntries(values, 'value');
  scopedAttributeValueEntriesCache.set(cacheKey, entries);
  return entries;
};

export const getDocumentLanguageId = (
  documentFlavor: SourceCodeDocumentFlavor,
): SourceCodeEditorLanguageId => {
  switch (documentFlavor) {
    case 'urdf':
    case 'xacro':
      return 'xml';
    case 'usd':
      return 'plaintext';
    case 'sdf':
    case 'mjcf':
    case 'equivalent-mjcf':
    default:
      return 'xml';
  }
};

export const supportsDocumentValidation = (
  documentFlavor: SourceCodeDocumentFlavor,
): boolean => (
  documentFlavor === 'urdf'
  || documentFlavor === 'xacro'
  || documentFlavor === 'sdf'
  || documentFlavor === 'mjcf'
  || documentFlavor === 'equivalent-mjcf'
);

export const isXmlLikeDocumentFlavor = (
  documentFlavor: SourceCodeDocumentFlavor,
): boolean => getDocumentLanguageId(documentFlavor) !== 'plaintext';

export const resolveXmlCompletionEntryForContext = (
  entry: XmlCompletionEntry,
  textBeforeCursor: string,
): XmlCompletionEntry => {
  if (entry.kind !== 'tag') {
    return entry;
  }

  if (!XML_OPENING_TAG_CONTEXT_PATTERN.test(textBeforeCursor)) {
    return entry;
  }

  if (XML_CLOSING_TAG_CONTEXT_PATTERN.test(textBeforeCursor)) {
    return entry;
  }

  const tagName = entry.insertText.trim();
  if (tagName.length === 0) {
    return entry;
  }

  return {
    ...entry,
    insertText: `${tagName}\${1}>$0</${tagName}>`,
    insertAsSnippet: true,
  };
};

export const getXmlCompletionEntries = (
  documentFlavor: SourceCodeDocumentFlavor,
  textBeforeCursor: string,
): XmlCompletionEntry[] => {
  if (
    documentFlavor !== 'urdf'
    && documentFlavor !== 'xacro'
    && documentFlavor !== 'sdf'
    && documentFlavor !== 'mjcf'
    && documentFlavor !== 'equivalent-mjcf'
  ) {
    return [];
  }

  const attributeValueMatch = textBeforeCursor.match(XML_ATTRIBUTE_VALUE_CONTEXT_PATTERN);
  if (attributeValueMatch) {
    return getScopedAttributeValueEntries(
      documentFlavor,
      attributeValueMatch[1],
      attributeValueMatch[2],
      textBeforeCursor,
    );
  }

  if (XML_ATTRIBUTE_CONTEXT_PATTERN.test(textBeforeCursor)) {
    const openTagMatch = textBeforeCursor.match(XML_OPEN_TAG_NAME_CONTEXT_PATTERN);
    return getScopedAttributeEntries(documentFlavor, openTagMatch?.[1] || null, textBeforeCursor);
  }

  if (XML_TAG_CONTEXT_PATTERN.test(textBeforeCursor)) {
    if (documentFlavor === 'urdf' || documentFlavor === 'xacro') {
      const scopedEntries = getScopedTagEntries(documentFlavor, getTagScope(textBeforeCursor));
      if (documentFlavor === 'xacro') {
        const macroDefinitions = getXacroMacroDefinitions(textBeforeCursor);
        const macroTagEntries = buildKeywordEntries(
          Array.from(macroDefinitions.keys()).map((macroName) => `xacro:${macroName}`),
          'tag',
        );
        return mergeCompletionEntries(scopedEntries, macroTagEntries);
      }
      return scopedEntries;
    }
    if (documentFlavor === 'sdf') {
      return getSdfScopedTagEntries(textBeforeCursor);
    }
    return getMjcfScopedTagEntries(textBeforeCursor);
  }

  return EMPTY_ENTRIES;
};
