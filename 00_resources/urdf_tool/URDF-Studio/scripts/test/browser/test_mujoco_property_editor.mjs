#!/usr/bin/env node

/**
 * MuJoCo/MJCF Property Editor browser regression test.
 *
 * Covers editable joint origin/axis/limit/dynamics/type fields, joint angle
 * control, viewer display flags, and tool mode switching on a real MJCF model.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual,
  importModel, waitForReady, getTopology,
  openSourceEditor, getSourceEditorText,
  store, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

const MODEL = { dir: 'franka_emika_panda', file: 'panda.xml' };
const T1_MODEL = { dir: 'booster_t1', file: 't1.xml' };
const EPSILON = 1e-9;

function closeTo(actual, expected, epsilon = EPSILON) {
  return typeof actual === 'number' && Number.isFinite(actual) && Math.abs(actual - expected) <= epsilon;
}

function assertClose(suite, actual, expected, message) {
  return assert(suite, closeTo(actual, expected), `${message} (expected ${expected}, got ${actual})`);
}

function vectorFrom(value, fallback) {
  if (Array.isArray(value) && value.length >= 3) return value;
  return fallback;
}

function pickEditableJoint(topo) {
  const movableTypes = new Set(['revolute', 'continuous', 'prismatic']);
  return (
    topo.joints.find((joint) => movableTypes.has(joint.type) && Array.isArray(joint.axis)) ??
    topo.joints.find((joint) => movableTypes.has(joint.type)) ??
    topo.joints.find((joint) => joint.type !== 'fixed') ??
    topo.joints[0]
  );
}

async function readViewer(page) {
  return page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.()?.viewer ?? null);
}

async function readRawJoint(page, jointId) {
  return page.evaluate((id) => {
    const state = window.__URDF_STUDIO_DEBUG__?.__workspaceStore__?.getState?.();
    const ref = state?.getSceneProjection?.()?.globalToEntityRef?.get(id) ?? null;
    const joint = ref?.type === 'joint'
      ? state?.workspace?.components?.[ref.componentId]?.robot?.joints?.[ref.entityId] ?? null
      : null;
    return joint
      ? {
          id: joint.id,
          name: joint.name,
          type: joint.type,
          angle: joint.angle,
        }
      : null;
  }, jointId);
}

async function prepareT1PhysicsEditor(page) {
  const deadline = Date.now() + 30_000;
  let lastProbe = { inputCount: 0, sidebarText: '' };

  while (Date.now() < deadline) {
    lastProbe = await page.evaluate(() => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const uiStore = api?.__uiStore__;
      const uiState = uiStore?.getState?.();
      uiStore?.setState?.({
        appMode: 'editor',
        detailLinkTab: 'physics',
        massInertiaChangeBehavior: 'preserve',
        rotationDisplayMode: 'euler_rad',
        sidebar: {
          ...(uiState?.sidebar ?? {}),
          rightCollapsed: false,
        },
      });
      const workspace = api?.__workspaceStore__?.getState?.()?.workspace ?? null;
      const component = Object.values(workspace?.components ?? {}).find((candidate) =>
        String(candidate?.sourceFile ?? '').endsWith('t1.xml')) ?? null;
      const selectionStore = api?.__selectionStore__?.getState?.();
      selectionStore?.setInteractionGuard?.(null);
      if (component?.robot?.links?.Trunk) {
        selectionStore?.setSelection?.({
          entity: { type: 'link', componentId: component.id, entityId: 'Trunk' },
        });
      }

      const sidebar = document.querySelector('[data-testid="property-editor-sidebar"]');
      const inputCount = [...document.querySelectorAll('[data-testid="property-editor-sidebar"] input')]
        .filter((input) => {
          const rect = input.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }).length;
      return {
        inputCount,
        sidebarText: sidebar?.textContent?.slice(0, 160) ?? '',
      };
    });

    if (lastProbe.inputCount > 10) {
      return;
    }

    await delay(500);
  }

  throw new Error(
    `Timed out waiting for T1 physics editor inputs ` +
      `(last: ${lastProbe.inputCount}, text: ${JSON.stringify(lastProbe.sidebarText)}).`,
  );
}

async function waitForT1RobotLoaded(page) {
  const deadline = Date.now() + 60_000;
  let last = null;

  while (Date.now() < deadline) {
    last = await page.evaluate(() => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const workspace = api?.__workspaceStore__?.getState?.()?.workspace ?? null;
      const documentLoadState = api?.getDocumentLoadState?.() ?? null;
      const component =
        Object.values(workspace?.components ?? {}).find((candidate) =>
          String(candidate?.sourceFile ?? '').endsWith('t1.xml')) ?? null;
      const rootLink = component?.robot?.links?.Trunk ?? null;

      return {
        documentLoadState,
        hasTrunk: Boolean(rootLink),
        rootMass: rootLink?.inertial?.mass ?? null,
        componentId: component?.id ?? null,
        componentSourceFile: component?.sourceFile ?? null,
      };
    });

    if (
      last.hasTrunk &&
      last.rootMass !== null &&
      Boolean(last.componentId) &&
      String(last.documentLoadState?.fileName ?? '').endsWith('t1.xml')
    ) {
      return;
    }

    if (last.documentLoadState?.status === 'error') {
      throw new Error(`T1 document load failed: ${last.documentLoadState.error ?? 'unknown'}`);
    }

    await delay(250);
  }

  throw new Error(`Timed out waiting for T1 robot store load (last: ${JSON.stringify(last)}).`);
}

async function waitForPandaRobotLoaded(page) {
  const deadline = Date.now() + 60_000;
  let last = null;

  while (Date.now() < deadline) {
    last = await page.evaluate(() => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const workspace = api?.__workspaceStore__?.getState?.()?.workspace ?? null;
      const documentLoadState = api?.getDocumentLoadState?.() ?? null;
      const component = Object.values(workspace?.components ?? {}).find((candidate) =>
        String(candidate?.sourceFile ?? '').endsWith('panda.xml')) ?? null;
      const links = component?.robot?.links ?? {};
      const joints = component?.robot?.joints ?? {};

      return {
        documentLoadState,
        hasBase: Boolean(links.panda_link0),
        hasJoint: Boolean(joints.panda_joint1),
        linkCount: Object.keys(links).length,
        jointCount: Object.keys(joints).length,
      };
    });

    if (
      last.linkCount === 11 &&
      last.jointCount === 10 &&
      String(last.documentLoadState?.fileName ?? '').endsWith('panda.xml')
    ) {
      return;
    }

    if (last.documentLoadState?.status === 'error') {
      throw new Error(`Panda document load failed: ${last.documentLoadState.error ?? 'unknown'}`);
    }

    await delay(250);
  }

  throw new Error(`Timed out waiting for Panda robot store load (last: ${JSON.stringify(last)}).`);
}

async function editVisiblePropertyInput(page, visibleIndex, value) {
  const selector = '[data-testid="property-editor-sidebar"] input';
  const target = await page.evaluateHandle((inputSelector, index) => {
    const isVisible = (input) => {
      const rect = input.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const inputs = [...document.querySelectorAll(inputSelector)].filter(isVisible);
    return inputs[index] ?? null;
  }, selector, visibleIndex);
  const element = target.asElement();
  if (!element) {
    throw new Error(`Visible property input ${visibleIndex} was not found.`);
  }

  await element.click({ clickCount: 3 });
  await page.keyboard.type(String(value));
  await page.keyboard.press('Enter');
  await delay(350);
  await target.dispose();
}

async function readT1TrunkPropertyState(page) {
  return page.evaluate(() => {
    const api = window.__URDF_STUDIO_DEBUG__;
    const workspace = api?.__workspaceStore__?.getState?.()?.workspace ?? null;
    const component =
      Object.values(workspace?.components ?? {}).find((candidate) =>
        String(candidate?.sourceFile ?? '').endsWith('t1.xml')) ?? null;
    const componentLink = component?.robot?.links?.Trunk ?? null;
    const rootLink = componentLink;
    const sourceDraft = component
      ? api?.__assetsStore__?.getState?.()?.componentSourceDrafts?.[component.id] ?? null
      : null;
    const visibleInputs = [...document.querySelectorAll('[data-testid="property-editor-sidebar"] input')]
      .filter((input) => {
        const rect = input.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      })
      .map((input) => input.value);

    return {
      rootMass: rootLink?.inertial?.mass ?? null,
      seedMass: componentLink?.inertial?.mass ?? null,
      rootComX: rootLink?.inertial?.origin?.xyz?.x ?? null,
      seedComX: componentLink?.inertial?.origin?.xyz?.x ?? null,
      rootRoll: rootLink?.inertial?.origin?.rpy?.r ?? null,
      seedRoll: componentLink?.inertial?.origin?.rpy?.r ?? null,
      componentId: component?.id ?? null,
      inputValues: visibleInputs,
      sourceContent: sourceDraft?.content ?? '',
    };
  });
}

async function runT1SourceScenePropertyRegression(suite, page, report) {
  await importModel(page, T1_MODEL.dir, T1_MODEL.file);
  await waitForReady(page);
  await waitForT1RobotLoaded(page);
  await prepareT1PhysicsEditor(page);

  const before = await readT1TrunkPropertyState(page);
  assert(suite, Boolean(before.componentId), 'T1 canonical component is present');
  assertClose(suite, before.rootMass, 11.7, 'T1 component mass baseline loaded');
  assertClose(suite, before.seedMass, 11.7, 'T1 canonical mass baseline loaded');

  await editVisiblePropertyInput(page, 6, '12.34');
  const afterMass = await readT1TrunkPropertyState(page);
  assertClose(suite, afterMass.rootMass, 12.34, 'T1 UI mass edit updates root robot');
  assertClose(suite, afterMass.seedMass, 12.34, 'T1 UI mass edit syncs seed component');
  assertClose(suite, Number(afterMass.inputValues[6]), 12.34, 'T1 mass input keeps committed value');
  assert(
    suite,
    afterMass.sourceContent.includes('mass="12.34"'),
    'T1 mass edit patches selected t1.xml source',
  );

  await editVisiblePropertyInput(page, 7, '0.123456');
  const afterCom = await readT1TrunkPropertyState(page);
  assertClose(suite, afterCom.rootMass, 12.34, 'T1 COM edit preserves root mass');
  assertClose(suite, afterCom.seedMass, 12.34, 'T1 COM edit preserves seed mass');
  assertClose(suite, afterCom.rootComX, 0.123456, 'T1 UI inertial COM X edit updates root robot');
  assertClose(suite, afterCom.seedComX, 0.123456, 'T1 UI inertial COM X edit syncs seed component');
  assert(
    suite,
    afterCom.sourceContent.includes('pos="0.123456 -0.000001 0.105062"'),
    'T1 inertial COM edit patches selected t1.xml source',
  );

  await editVisiblePropertyInput(page, 10, '0.222');
  await delay(500);
  const afterRoll = await readT1TrunkPropertyState(page);
  assertClose(suite, afterRoll.rootMass, 12.34, 'T1 roll edit preserves root mass');
  assertClose(suite, afterRoll.seedMass, 12.34, 'T1 roll edit preserves seed mass');
  assertClose(suite, afterRoll.rootRoll, 0.222, 'T1 UI inertial roll edit updates root robot');
  assertClose(suite, afterRoll.seedRoll, 0.222, 'T1 UI inertial roll edit syncs seed component');

  await store.undo(page);
  await delay(300);
  const afterUndo = await readT1TrunkPropertyState(page);
  assertClose(suite, afterUndo.rootRoll, before.rootRoll, 'T1 source-scene undo restores root roll');
  assertClose(suite, afterUndo.seedRoll, before.seedRoll, 'T1 source-scene undo restores seed roll');

  await store.redo(page);
  await delay(300);
  const afterRedo = await readT1TrunkPropertyState(page);
  assertClose(suite, afterRedo.rootRoll, 0.222, 'T1 source-scene redo restores root roll edit');
  assertClose(suite, afterRedo.seedRoll, 0.222, 'T1 source-scene redo restores seed roll edit');

  await openSourceEditor(page);
  const sourceEditorText = await getSourceEditorText(page);
  assert(suite, sourceEditorText.includes('mass="12.34"'), 'T1 Source Code panel shows patched mass');
  assert(
    suite,
    sourceEditorText.includes('pos="0.123456 -0.000001 0.105062"'),
    'T1 Source Code panel shows patched inertial COM',
  );

  report.t1 = {
    componentId: before.componentId,
    mass: afterMass.rootMass,
    comX: afterCom.rootComX,
    roll: afterRoll.rootRoll,
  };
}

async function main() {
  const suite = createTestSuite('MuJoCo MJCF Property Editor');
  const report = {};

  const session = await createSession();
  const { page } = session;
  try {
    await runT1SourceScenePropertyRegression(suite, page, report);

    const t1Errs = session.errors();
    assert(suite, t1Errs.page.length === 0, `no T1 page errors (${t1Errs.page.length})`);

    await importModel(page, MODEL.dir, MODEL.file);
    await waitForReady(page);
    await waitForPandaRobotLoaded(page);
    const base = await getTopology(page);
    report.baseline = { linkCount: base.linkCount, jointCount: base.jointCount, name: base.name };
    console.log(`  Baseline: ${base.linkCount}L ${base.jointCount}J`);

    const joint = pickEditableJoint(base);
    assert(suite, !!joint, 'editable joint selected from topology');
    assert(suite, Boolean(joint?.name), 'selected joint has a name');
    assert(suite, Boolean(joint?.id), 'selected joint has an id');

    const originalType = joint.type;
    const originalOriginXyz = vectorFrom(joint.originXyz, [0, 0, 0]);
    const originalOriginRpy = vectorFrom(joint.originRpy, [0, 0, 0]);
    const originalAxis = vectorFrom(joint.axis, [0, 0, 1]);

    // 1. Joint origin editing.
    await store.updateJoint(page, joint.id, {
      origin: { xyz: { x: 0.11, y: -0.22, z: 0.33 }, rpy: { r: 0.04, p: -0.05, y: 0.06 } },
    });
    await delay(200);
    const afterOrigin = await getTopology(page);
    const originJoint = afterOrigin.joints.find((candidate) => candidate.id === joint.id);
    assertClose(suite, originJoint?.originXyz?.[0], 0.11, 'joint origin xyz[0] updated');
    assertClose(suite, originJoint?.originXyz?.[1], -0.22, 'joint origin xyz[1] updated');
    assertClose(suite, originJoint?.originRpy?.[2], 0.06, 'joint origin rpy[2] updated');

    await store.updateJoint(page, joint.id, {
      origin: {
        xyz: { x: originalOriginXyz[0], y: originalOriginXyz[1], z: originalOriginXyz[2] },
        rpy: { r: originalOriginRpy[0], p: originalOriginRpy[1], y: originalOriginRpy[2] },
      },
    });
    await delay(200);

    // 2. Joint axis editing.
    await store.updateJoint(page, joint.id, { axis: { x: 0, y: 0, z: 1 } });
    await delay(200);
    const afterAxis = await getTopology(page);
    const axisJoint = afterAxis.joints.find((candidate) => candidate.id === joint.id);
    assertClose(suite, axisJoint?.axis?.[0], 0, 'joint axis x updated');
    assertClose(suite, axisJoint?.axis?.[1], 0, 'joint axis y updated');
    assertClose(suite, axisJoint?.axis?.[2], 1, 'joint axis z updated');

    await store.updateJoint(page, joint.id, {
      axis: { x: originalAxis[0], y: originalAxis[1], z: originalAxis[2] },
    });
    await delay(200);

    // 3. Joint limit editing.
    await store.updateJoint(page, joint.id, {
      limit: { lower: -0.45, upper: 0.45, effort: 30, velocity: 9 },
    });
    await delay(200);
    const afterLimit = await getTopology(page);
    const limitJoint = afterLimit.joints.find((candidate) => candidate.id === joint.id);
    assertClose(suite, limitJoint?.limit?.lower, -0.45, 'joint limit lower updated');
    assertClose(suite, limitJoint?.limit?.upper, 0.45, 'joint limit upper updated');
    assertClose(suite, limitJoint?.limit?.effort, 30, 'joint limit effort updated');
    assertClose(suite, limitJoint?.limit?.velocity, 9, 'joint limit velocity updated');

    // 4. Joint dynamics editing.
    await store.updateJoint(page, joint.id, {
      dynamics: { damping: 4.5, friction: 0.25 },
    });
    await delay(200);
    const afterDynamics = await getTopology(page);
    const dynamicsJoint = afterDynamics.joints.find((candidate) => candidate.id === joint.id);
    assertClose(suite, dynamicsJoint?.damping, 4.5, 'joint dynamics damping updated');
    assertClose(suite, dynamicsJoint?.friction, 0.25, 'joint dynamics friction updated');

    // 5. Joint type editing and undo restore.
    const nextType = originalType === 'continuous' ? 'revolute' : 'continuous';
    await store.updateJoint(page, joint.id, { type: nextType });
    await delay(200);
    const afterType = await getTopology(page);
    assertEqual(suite, afterType.joints.find((candidate) => candidate.id === joint.id)?.type,
      nextType, 'joint type updated');

    await store.undo(page);
    await delay(200);
    const afterTypeUndo = await getTopology(page);
    assertEqual(suite, afterTypeUndo.joints.find((candidate) => candidate.id === joint.id)?.type,
      originalType, 'joint type undo restores original type');

    // 6. Joint angle control through store and viewer debug path.
    const angleResult = await store.setJointAngle(page, joint.name, 0.25);
    await delay(200);
    assert(suite, angleResult?.ok, 'setJointAngle returns ok');
    const afterAngle = await readRawJoint(page, joint.id);
    assertClose(suite, afterAngle?.angle, 0.25, 'joint angle persisted in robot store');

    const viewerAngleResult = await store.setJointAngles(page, { [joint.name]: -0.2 });
    await delay(200);
    assert(suite, viewerAngleResult?.ok, 'setViewerJointAngles returns ok');
    const viewerAfterAngle = await readViewer(page);
    assert(suite, closeTo(viewerAfterAngle?.jointAngles?.[joint.name], -0.2) ||
      closeTo(viewerAfterAngle?.jointAngles?.[joint.id], -0.2),
      'viewer joint angle updated');

    // 7. Viewer flags.
    const flagsOn = await store.setViewerFlags(page, {
      showCollision: true,
      showJointAxes: true,
      showOrigins: true,
      showCenterOfMass: true,
      modelOpacity: 0.65,
    });
    await delay(200);
    assert(suite, flagsOn?.ok, 'setViewerFlags on returns ok');
    const viewerFlagsOn = await readViewer(page);
    assert(suite, viewerFlagsOn?.flags?.showCollision === true, 'viewer showCollision enabled');
    assert(suite, viewerFlagsOn?.flags?.showJointAxes === true, 'viewer showJointAxes enabled');
    assert(suite, viewerFlagsOn?.flags?.showOrigins === true, 'viewer showOrigins enabled');
    assert(suite, viewerFlagsOn?.flags?.showCenterOfMass === true, 'viewer showCenterOfMass enabled');
    assertClose(suite, viewerFlagsOn?.flags?.modelOpacity, 0.65, 'viewer modelOpacity updated');

    const flagsOff = await store.setViewerFlags(page, {
      showCollision: false,
      showJointAxes: false,
      showOrigins: false,
      showCenterOfMass: false,
      modelOpacity: 1,
    });
    await delay(200);
    assert(suite, flagsOff?.ok, 'setViewerFlags off returns ok');
    const viewerFlagsOff = await readViewer(page);
    assert(suite, viewerFlagsOff?.flags?.showCollision === false, 'viewer showCollision disabled');
    assert(suite, viewerFlagsOff?.flags?.showJointAxes === false, 'viewer showJointAxes disabled');
    assertClose(suite, viewerFlagsOff?.flags?.modelOpacity, 1, 'viewer modelOpacity restored');

    // 8. Tool mode switching.
    const translateMode = await store.setViewerToolMode(page, 'translate');
    await delay(200);
    assert(suite, translateMode?.ok, 'tool mode translate returns ok');
    assertEqual(suite, translateMode?.activeMode, 'translate', 'tool mode translate resolves active mode');

    const selectMode = await store.setViewerToolMode(page, 'select');
    await delay(200);
    assert(suite, selectMode?.ok, 'tool mode select returns ok');
    assertEqual(suite, selectMode?.activeMode, 'select', 'tool mode select resolves active mode');

    const finalTopo = await getTopology(page);
    report.selectedJoint = { id: joint.id, name: joint.name, originalType };
    report.final = { linkCount: finalTopo.linkCount, jointCount: finalTopo.jointCount };
    assertEqual(suite, finalTopo.linkCount, base.linkCount, 'topology link count unchanged');
    assertEqual(suite, finalTopo.jointCount, base.jointCount, 'topology joint count unchanged');

    const pandaErrs = session.errors();
    assert(suite, pandaErrs.page.length === 0, `no page errors (${pandaErrs.page.length})`);
  } finally {
    await session.cleanup();
  }

  await writeReport('mujoco_property_editor', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
