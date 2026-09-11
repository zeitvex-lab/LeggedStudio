import { parseMJCF } from '@/core/parsers/mjcf/mjcfParser';
import { parseJoints } from '@/core/parsers/urdf/parser/jointParser';
import { parseLinks } from '@/core/parsers/urdf/parser/linkParser';
import { parseMaterials } from '@/core/parsers/urdf/parser/materialParser';
import type { SourceCodeDirtyRange } from '@/features/code-editor';
import type { RobotFile, RobotState, UrdfJoint, UrdfLink } from '@/types';
import type { EditableSourceIncrementalPatch } from './editableSourceIncrementalPatch';

export interface DetectEditableSourceIncrementalPatchOptions {
  file: Pick<RobotFile, 'format' | 'name'> | null | undefined;
  previousContent: string;
  nextContent: string;
  dirtyRanges: SourceCodeDirtyRange[];
  skipMjcfPatch?: boolean;
}

export interface EditableSourceIncrementalPatchDiagnostics {
  attempted: boolean;
  dirtyRangeCount: number;
  dirtySpanBytes: number;
  dirtySpanLimitBytes: number;
  patchKind: EditableSourceIncrementalPatch['kind'] | null;
  skipReason: string | null;
}

export interface EditableSourceIncrementalPatchDetectionResult {
  patch: EditableSourceIncrementalPatch | null;
  diagnostics: EditableSourceIncrementalPatchDiagnostics;
}

interface XmlElementBounds {
  tagName: string;
  startOffset: number;
  endOffset: number;
  parentTagName: string | null;
}

interface UrdfParseContext {
  globalMaterials: ReturnType<typeof parseMaterials>['globalMaterials'];
  linkGazeboMaterials: ReturnType<typeof parseMaterials>['linkGazeboMaterials'];
}

const XML_TOKEN_RE =
  /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[[\s\S]*?\]\]>|<\/?([A-Za-z_][\w:.-]*)\b[^>]*?>/g;
const MJCF_PATCH_ROOT_NAME = '__editable_source_patch_root__';
const MAX_INCREMENTAL_DIRTY_RANGE_COUNT = 4;
const MAX_INCREMENTAL_DIRTY_SPAN_BYTES = 4096;
const MAX_INCREMENTAL_DIRTY_SPAN_RATIO = 0.05;

function normalizeDirtyRange(range: SourceCodeDirtyRange): SourceCodeDirtyRange {
  const startOffset = Math.max(0, Math.min(range.startOffset, range.endOffset));
  const endOffset = Math.max(startOffset, Math.max(range.startOffset, range.endOffset));
  return { startOffset, endOffset };
}

function mergeDirtyRanges(ranges: SourceCodeDirtyRange[]): SourceCodeDirtyRange[] {
  if (ranges.length === 0) {
    return [];
  }

  const sortedRanges = ranges
    .map(normalizeDirtyRange)
    .sort((left, right) => left.startOffset - right.startOffset);
  const mergedRanges: SourceCodeDirtyRange[] = [sortedRanges[0]];

  for (let index = 1; index < sortedRanges.length; index += 1) {
    const nextRange = sortedRanges[index];
    const currentRange = mergedRanges[mergedRanges.length - 1];

    if (nextRange.startOffset <= currentRange.endOffset) {
      currentRange.endOffset = Math.max(currentRange.endOffset, nextRange.endOffset);
      continue;
    }

    mergedRanges.push(nextRange);
  }

  return mergedRanges;
}

function computeDirtySpanLimitBytes(nextContentLength: number): number {
  return Math.max(
    1,
    Math.ceil(
      Math.min(
        MAX_INCREMENTAL_DIRTY_SPAN_BYTES,
        Math.max(1, nextContentLength) * MAX_INCREMENTAL_DIRTY_SPAN_RATIO,
      ),
    ),
  );
}

export function buildEditableSourceIncrementalPatchDiagnostics(
  options: Pick<
    DetectEditableSourceIncrementalPatchOptions,
    'previousContent' | 'nextContent' | 'dirtyRanges'
  > & {
    attempted?: boolean;
    patchKind?: EditableSourceIncrementalPatch['kind'] | null;
    skipReason?: string | null;
  },
): EditableSourceIncrementalPatchDiagnostics {
  const mergedDirtyRanges = mergeDirtyRanges(options.dirtyRanges);
  const nextDirtySpanBytes = mergedDirtyRanges.reduce(
    (total, range) => total + Math.max(0, range.endOffset - range.startOffset),
    0,
  );
  const contentLengthDelta = Math.abs(options.nextContent.length - options.previousContent.length);

  return {
    attempted: options.attempted ?? false,
    dirtyRangeCount: mergedDirtyRanges.length,
    dirtySpanBytes: Math.max(nextDirtySpanBytes, contentLengthDelta),
    dirtySpanLimitBytes: computeDirtySpanLimitBytes(options.nextContent.length),
    patchKind: options.patchKind ?? null,
    skipReason: options.skipReason ?? null,
  };
}

function buildPatchResult(
  patch: EditableSourceIncrementalPatch,
  diagnostics: EditableSourceIncrementalPatchDiagnostics,
): EditableSourceIncrementalPatchDetectionResult {
  return {
    patch,
    diagnostics: {
      ...diagnostics,
      attempted: true,
      patchKind: patch.kind,
      skipReason: null,
    },
  };
}

function buildSkipResult(
  diagnostics: EditableSourceIncrementalPatchDiagnostics,
  skipReason: string,
): EditableSourceIncrementalPatchDetectionResult {
  return {
    patch: null,
    diagnostics: {
      ...diagnostics,
      attempted: true,
      patchKind: null,
      skipReason,
    },
  };
}

function evaluateIncrementalPatchEligibility(
  options: DetectEditableSourceIncrementalPatchOptions,
): EditableSourceIncrementalPatchDetectionResult | null {
  const diagnostics = buildEditableSourceIncrementalPatchDiagnostics({
    previousContent: options.previousContent,
    nextContent: options.nextContent,
    dirtyRanges: options.dirtyRanges,
    attempted: true,
  });

  if (!options.file) {
    return buildSkipResult(diagnostics, 'missing-file');
  }

  if (diagnostics.dirtyRangeCount === 0) {
    return buildSkipResult(diagnostics, 'no-dirty-ranges');
  }

  if (diagnostics.dirtyRangeCount > MAX_INCREMENTAL_DIRTY_RANGE_COUNT) {
    return buildSkipResult(diagnostics, 'too-many-dirty-ranges');
  }

  if (options.file.format === 'mjcf') {
    if (options.skipMjcfPatch) {
      return buildSkipResult(diagnostics, 'mjcf-patch-skipped');
    }

    if (/<include\b/i.test(options.previousContent) || /<include\b/i.test(options.nextContent)) {
      return buildSkipResult(diagnostics, 'mjcf-include');
    }
  }

  if (diagnostics.dirtySpanBytes > diagnostics.dirtySpanLimitBytes) {
    return buildSkipResult(diagnostics, 'dirty-span-too-large');
  }

  if (options.file.format !== 'urdf' && options.file.format !== 'mjcf') {
    return buildSkipResult(diagnostics, 'unsupported-format');
  }

  return null;
}

function parseXmlRootElement(xml: string, rootTagName: string): Element | null {
  const doc = new DOMParser().parseFromString(xml, 'text/xml');
  if (doc.querySelector('parsererror')) {
    return null;
  }

  return doc.querySelector(rootTagName);
}

function buildUrdfParseContext(xml: string): UrdfParseContext | null {
  const robotEl = parseXmlRootElement(xml, 'robot');
  if (!robotEl) {
    return null;
  }

  return parseMaterials(robotEl);
}

function collectXmlElementBounds(xml: string): XmlElementBounds[] {
  const bounds: XmlElementBounds[] = [];
  const stack: Array<{
    tagName: string;
    startOffset: number;
    parentTagName: string | null;
  }> = [];

  XML_TOKEN_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = XML_TOKEN_RE.exec(xml)) !== null) {
    const rawTag = match[0];
    const tagName = match[1];

    if (!tagName) {
      continue;
    }

    if (rawTag.startsWith('</')) {
      const openTag = stack.pop();
      if (!openTag || openTag.tagName !== tagName) {
        continue;
      }

      bounds.push({
        tagName,
        startOffset: openTag.startOffset,
        endOffset: match.index + rawTag.length,
        parentTagName: openTag.parentTagName,
      });
      continue;
    }

    const parentTagName = stack[stack.length - 1]?.tagName ?? null;
    const selfClosing = /\/\s*>$/.test(rawTag);
    if (selfClosing) {
      bounds.push({
        tagName,
        startOffset: match.index,
        endOffset: match.index + rawTag.length,
        parentTagName,
      });
      continue;
    }

    stack.push({
      tagName,
      startOffset: match.index,
      parentTagName,
    });
  }

  return bounds;
}

function overlapsRange(element: XmlElementBounds, range: SourceCodeDirtyRange): boolean {
  return range.startOffset >= element.startOffset && range.endOffset <= element.endOffset;
}

function sameElementBounds(left: XmlElementBounds, right: XmlElementBounds): boolean {
  return (
    left.tagName === right.tagName &&
    left.startOffset === right.startOffset &&
    left.endOffset === right.endOffset &&
    left.parentTagName === right.parentTagName
  );
}

function sameSortedStrings(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  const sortedLeft = [...left].sort();
  const sortedRight = [...right].sort();
  return sortedLeft.every((value, index) => value === sortedRight[index]);
}

function sortedStrings(values: string[]): string[] {
  return [...values].sort();
}

function findChangedUrdfTopLevelElement(
  xml: string,
  dirtyRanges: SourceCodeDirtyRange[],
): {
  element: XmlElementBounds;
  indexByTag: number;
} | null {
  const topLevelElements = collectXmlElementBounds(xml).filter(
    (element) =>
      element.parentTagName === 'robot' &&
      (element.tagName === 'link' || element.tagName === 'joint'),
  );

  if (topLevelElements.length === 0) {
    return null;
  }

  const changedElements = dirtyRanges
    .map((range) => {
      const matchingElements = topLevelElements
        .filter((element) => overlapsRange(element, range))
        .sort(
          (left, right) =>
            left.endOffset - left.startOffset - (right.endOffset - right.startOffset),
        );
      return matchingElements[0] ?? null;
    })
    .filter((element): element is XmlElementBounds => Boolean(element));

  if (changedElements.length === 0) {
    return null;
  }

  const uniqueElementKeys = new Set(
    changedElements.map(
      (element) => `${element.tagName}:${element.startOffset}:${element.endOffset}`,
    ),
  );
  if (uniqueElementKeys.size !== 1) {
    return null;
  }

  const element = changedElements[0];
  const indexByTag = topLevelElements
    .filter((candidate) => candidate.tagName === element.tagName)
    .findIndex(
      (candidate) =>
        candidate.startOffset === element.startOffset && candidate.endOffset === element.endOffset,
    );

  if (indexByTag < 0) {
    return null;
  }

  return { element, indexByTag };
}

function resolvePreviousUrdfTopLevelElement(
  xml: string,
  tagName: 'link' | 'joint',
  indexByTag: number,
): XmlElementBounds | null {
  const topLevelElements = collectXmlElementBounds(xml).filter(
    (element) => element.parentTagName === 'robot' && element.tagName === tagName,
  );

  return topLevelElements[indexByTag] ?? null;
}

function findChangedMjcfBodyElement(
  xml: string,
  dirtyRanges: SourceCodeDirtyRange[],
): {
  element: XmlElementBounds;
  bodyIndex: number;
} | null {
  const bodyElements = collectXmlElementBounds(xml)
    .filter((element) => element.tagName === 'body')
    .sort((left, right) => left.startOffset - right.startOffset);

  if (bodyElements.length === 0) {
    return null;
  }

  const changedElements = dirtyRanges
    .map((range) => {
      const matchingBodies = bodyElements
        .filter((element) => overlapsRange(element, range))
        .sort(
          (left, right) =>
            left.endOffset - left.startOffset - (right.endOffset - right.startOffset),
        );
      return matchingBodies[0] ?? null;
    })
    .filter((element): element is XmlElementBounds => Boolean(element));

  if (changedElements.length === 0) {
    return null;
  }

  const referenceBody = changedElements[0];
  if (!changedElements.every((candidate) => sameElementBounds(candidate, referenceBody))) {
    return null;
  }

  const bodyIndex = bodyElements.findIndex((candidate) =>
    sameElementBounds(candidate, referenceBody),
  );
  if (bodyIndex < 0) {
    return null;
  }

  return {
    element: referenceBody,
    bodyIndex,
  };
}

function resolvePreviousMjcfBodyElement(xml: string, bodyIndex: number): XmlElementBounds | null {
  return (
    collectXmlElementBounds(xml)
      .filter((element) => element.tagName === 'body')
      .sort((left, right) => left.startOffset - right.startOffset)[bodyIndex] ?? null
  );
}

function parseSingleUrdfLinkFragment(fragment: string, context: UrdfParseContext): UrdfLink | null {
  const robotEl = parseXmlRootElement(`<robot>${fragment}</robot>`, 'robot');
  if (!robotEl) {
    return null;
  }

  const { links } = parseLinks(robotEl, context.globalMaterials, context.linkGazeboMaterials);
  const parsedLinks = Object.values(links);
  return parsedLinks.length === 1 ? parsedLinks[0] : null;
}

function parseSingleUrdfJointFragment(fragment: string): UrdfJoint | null {
  const robotEl = parseXmlRootElement(`<robot>${fragment}</robot>`, 'robot');
  if (!robotEl) {
    return null;
  }

  const joints = parseJoints(robotEl);
  const parsedJoints = Object.values(joints);
  return parsedJoints.length === 1 ? parsedJoints[0] : null;
}

function parseSingleMjcfBodyName(fragment: string): string | null {
  const bodyEl = parseXmlRootElement(
    `<mujoco model="editable_source_patch"><worldbody>${fragment}</worldbody></mujoco>`,
    'body',
  );
  const bodyName = bodyEl?.getAttribute('name')?.trim();
  return bodyName || null;
}

function extractDirectRootChildFragments(xml: string, rootTagName: string): string[] | null {
  const rootEl = parseXmlRootElement(xml, rootTagName);
  if (!rootEl) {
    return null;
  }

  return collectXmlElementBounds(xml)
    .filter((element) => element.parentTagName === rootTagName)
    .sort((left, right) => left.startOffset - right.startOffset)
    .map((element) => xml.slice(element.startOffset, element.endOffset));
}

function buildMjcfBodyPatchDocument(xml: string, bodyFragment: string): string | null {
  const rootChildFragments = extractDirectRootChildFragments(xml, 'mujoco');
  if (!rootChildFragments) {
    return null;
  }

  if (rootChildFragments.some((fragment) => /<include\b/i.test(fragment))) {
    return null;
  }

  const preservedTopLevelFragments = rootChildFragments.filter(
    (fragment) => !/^<worldbody\b/i.test(fragment.trim()),
  );

  return [
    '<mujoco model="editable_source_patch">',
    ...preservedTopLevelFragments,
    '<worldbody>',
    `<body name="${MJCF_PATCH_ROOT_NAME}">`,
    bodyFragment,
    '</body>',
    '</worldbody>',
    '</mujoco>',
  ].join('\n');
}

function parseMjcfBodyPatchState(xml: string, bodyFragment: string): RobotState | null {
  const patchDocument = buildMjcfBodyPatchDocument(xml, bodyFragment);
  if (!patchDocument) {
    return null;
  }

  return parseMJCF(patchDocument);
}

function detectUrdfPatch(
  options: DetectEditableSourceIncrementalPatchOptions,
  diagnostics: EditableSourceIncrementalPatchDiagnostics,
): EditableSourceIncrementalPatchDetectionResult {
  const nextContext = buildUrdfParseContext(options.nextContent);
  const previousContext = buildUrdfParseContext(options.previousContent);
  if (!nextContext || !previousContext) {
    return buildSkipResult(diagnostics, 'urdf-document-parse-failed');
  }

  const nextChangedElement = findChangedUrdfTopLevelElement(
    options.nextContent,
    options.dirtyRanges,
  );
  if (!nextChangedElement) {
    return buildSkipResult(diagnostics, 'urdf-range-outside-single-top-level-element');
  }

  const previousChangedElement = resolvePreviousUrdfTopLevelElement(
    options.previousContent,
    nextChangedElement.element.tagName as 'link' | 'joint',
    nextChangedElement.indexByTag,
  );
  if (!previousChangedElement) {
    return buildSkipResult(diagnostics, 'urdf-previous-element-not-found');
  }

  const nextFragment = options.nextContent.slice(
    nextChangedElement.element.startOffset,
    nextChangedElement.element.endOffset,
  );
  const previousFragment = options.previousContent.slice(
    previousChangedElement.startOffset,
    previousChangedElement.endOffset,
  );

  if (nextChangedElement.element.tagName === 'link') {
    const previousLink = parseSingleUrdfLinkFragment(previousFragment, previousContext);
    const nextLink = parseSingleUrdfLinkFragment(nextFragment, nextContext);
    if (!previousLink || !nextLink) {
      return buildSkipResult(diagnostics, 'urdf-link-fragment-parse-failed');
    }

    return buildPatchResult(
      {
        kind: 'urdf-link-fragment-update',
        previousLinkId: previousLink.id,
        previousLinkName: previousLink.name,
        nextLink,
      },
      diagnostics,
    );
  }

  const previousJoint = parseSingleUrdfJointFragment(previousFragment);
  const nextJoint = parseSingleUrdfJointFragment(nextFragment);
  if (!previousJoint || !nextJoint) {
    return buildSkipResult(diagnostics, 'urdf-joint-fragment-parse-failed');
  }

  return buildPatchResult(
    {
      kind: 'urdf-joint-fragment-update',
      previousJointId: previousJoint.id,
      previousJointName: previousJoint.name,
      previousParentLinkId: previousJoint.parentLinkId,
      previousChildLinkId: previousJoint.childLinkId,
      nextJoint,
    },
    diagnostics,
  );
}

function detectMjcfPatch(
  options: DetectEditableSourceIncrementalPatchOptions,
  diagnostics: EditableSourceIncrementalPatchDiagnostics,
): EditableSourceIncrementalPatchDetectionResult {
  const nextChangedBody = findChangedMjcfBodyElement(options.nextContent, options.dirtyRanges);
  if (!nextChangedBody) {
    return buildSkipResult(diagnostics, 'mjcf-range-outside-single-body');
  }

  const previousChangedBody = resolvePreviousMjcfBodyElement(
    options.previousContent,
    nextChangedBody.bodyIndex,
  );
  if (!previousChangedBody) {
    return buildSkipResult(diagnostics, 'mjcf-previous-body-not-found');
  }

  const nextFragment = options.nextContent.slice(
    nextChangedBody.element.startOffset,
    nextChangedBody.element.endOffset,
  );
  const previousFragment = options.previousContent.slice(
    previousChangedBody.startOffset,
    previousChangedBody.endOffset,
  );

  const previousBodyName = parseSingleMjcfBodyName(previousFragment);
  const nextBodyName = parseSingleMjcfBodyName(nextFragment);
  if (!previousBodyName || !nextBodyName || previousBodyName !== nextBodyName) {
    return buildSkipResult(diagnostics, 'mjcf-body-renamed');
  }

  if (/<site\b/i.test(previousFragment) || /<site\b/i.test(nextFragment)) {
    return buildSkipResult(diagnostics, 'mjcf-site');
  }

  const previousPatchState = parseMjcfBodyPatchState(options.previousContent, previousFragment);
  const nextPatchState = parseMjcfBodyPatchState(options.nextContent, nextFragment);
  if (!previousPatchState || !nextPatchState) {
    return buildSkipResult(diagnostics, 'mjcf-body-patch-parse-failed');
  }

  const previousLinks = Object.entries(previousPatchState.links).filter(
    ([, link]) => link.name !== MJCF_PATCH_ROOT_NAME,
  );
  const nextLinks = Object.entries(nextPatchState.links).filter(
    ([, link]) => link.name !== MJCF_PATCH_ROOT_NAME,
  );
  const previousJoints = Object.entries(previousPatchState.joints);
  const nextJoints = Object.entries(nextPatchState.joints);
  const previousLinkNames = previousLinks.map(([, link]) => link.name);
  const nextLinkNames = nextLinks.map(([, link]) => link.name);
  const previousJointNames = previousJoints.map(([, joint]) => joint.name);
  const nextJointNames = nextJoints.map(([, joint]) => joint.name);

  if (
    !sameSortedStrings(previousLinkNames, nextLinkNames) ||
    !sameSortedStrings(previousJointNames, nextJointNames)
  ) {
    return buildSkipResult(diagnostics, 'mjcf-structural-subtree-change');
  }

  const nextLinksByName: Record<string, UrdfLink> = {};
  const nextJointsByName: Record<string, UrdfJoint> = {};
  const previousJointEndpointsByName: Record<
    string,
    { parentLinkId: string; childLinkId: string }
  > = {};

  for (const [, link] of nextLinks) {
    nextLinksByName[link.name] = link;
  }

  for (const [, joint] of nextJoints) {
    nextJointsByName[joint.name] = joint;
  }

  for (const [, joint] of previousJoints) {
    previousJointEndpointsByName[joint.name] = {
      parentLinkId: joint.parentLinkId,
      childLinkId: joint.childLinkId,
    };
  }

  return buildPatchResult(
    {
      kind: 'mjcf-body-subtree-update',
      stableLinkNames: sortedStrings(previousLinkNames),
      stableJointNames: sortedStrings(previousJointNames),
      previousJointEndpointsByName,
      nextLinksByName,
      nextJointsByName,
    },
    diagnostics,
  );
}

export function detectEditableSourceIncrementalPatchWithDiagnostics(
  options: DetectEditableSourceIncrementalPatchOptions,
): EditableSourceIncrementalPatchDetectionResult {
  const ineligibleResult = evaluateIncrementalPatchEligibility(options);
  if (ineligibleResult) {
    return ineligibleResult;
  }
  const file = options.file;
  if (!file) {
    const diagnostics = buildEditableSourceIncrementalPatchDiagnostics({
      previousContent: options.previousContent,
      nextContent: options.nextContent,
      dirtyRanges: options.dirtyRanges,
      attempted: true,
    });
    return buildSkipResult(diagnostics, 'missing-file');
  }

  const diagnostics = buildEditableSourceIncrementalPatchDiagnostics({
    previousContent: options.previousContent,
    nextContent: options.nextContent,
    dirtyRanges: options.dirtyRanges,
    attempted: true,
  });

  if (file.format === 'urdf') {
    return detectUrdfPatch(options, diagnostics);
  }

  if (file.format === 'mjcf') {
    return detectMjcfPatch(options, diagnostics);
  }

  return buildSkipResult(diagnostics, 'unsupported-format');
}

export function detectEditableSourceIncrementalPatch(
  options: DetectEditableSourceIncrementalPatchOptions,
): EditableSourceIncrementalPatch | null {
  return detectEditableSourceIncrementalPatchWithDiagnostics(options).patch;
}
