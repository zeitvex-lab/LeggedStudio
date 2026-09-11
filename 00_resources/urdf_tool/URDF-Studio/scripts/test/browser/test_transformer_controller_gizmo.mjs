#!/usr/bin/env node

/**
 * Transformer controller browser regression.
 *
 * Covers: CAD-style rotate arcs with direct ring dragging, screen E ring,
 * translate plane/center handles, universal-mode simplification, and stable
 * world sizing across camera zoom.
 */

import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession, createTestSuite, assert, assertGreaterThan,
  waitForReady, getProjectedInteractionTargets,
  store, writeReport, printSummary, assertNoBrowserErrors,
} from './helpers/urdf-helpers.mjs';
import { isTransientPageContextError } from '../helpers/browser-helpers.mjs';

const MODEL = {
  file: 'transformer_controller_fixture.urdf',
  content: `<?xml version="1.0"?>
<robot name="transformer_controller_fixture">
  <link name="base_link">
    <visual>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><box size="0.5 0.3 0.2"/></geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><box size="0.5 0.3 0.2"/></geometry>
    </collision>
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="1"/>
      <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/>
    </inertial>
  </link>
  <joint name="base_to_tool" type="fixed">
    <parent link="base_link"/>
    <child link="tool_link"/>
    <origin xyz="0.42 0 0.08" rpy="0 0 0"/>
  </joint>
  <link name="tool_link">
    <visual>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><box size="0.18 0.16 0.14"/></geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><box size="0.18 0.16 0.14"/></geometry>
    </collision>
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="0.5"/>
      <inertia ixx="0.005" ixy="0" ixz="0" iyy="0.005" iyz="0" izz="0.005"/>
    </inertial>
  </link>
</robot>`,
};
const SCREEN_RADIUS_CHANGE_RELATIVE_MIN = 0.08;
const WORLD_RADIUS_STABLE_RELATIVE_EPSILON = 0.02;
const ZOOM_WHEEL_DELTA_Y = -700;
const ZOOM_WHEEL_STEPS = 3;
const ORIGIN_ROTATE_FRONT_ARC_WORLD_RADIUS_MAX = 0.24;
const ORIGIN_ROTATE_E_RING_WORLD_RADIUS_MAX = 0.28;

function relativeDelta(left, right) {
  return Math.abs(Number(left) - Number(right)) / Math.max(1e-9, Math.abs(Number(left)));
}

async function evaluateWithTransientRetry(page, pageFunction, ...args) {
  let lastError = null;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      return await page.evaluate(pageFunction, ...args);
    } catch (error) {
      if (!isTransientPageContextError(error)) {
        throw error;
      }
      lastError = error;
      await delay(150 + attempt * 100);
    }
  }

  throw lastError;
}

async function seedAndLoadModel(page, model) {
  await page.waitForFunction(
    () =>
      Boolean(
        window.__URDF_STUDIO_DEBUG__?.resetFixtureFiles &&
        window.__URDF_STUDIO_DEBUG__?.seedFixtureFile &&
        window.__URDF_STUDIO_DEBUG__?.loadRobotByName,
      ),
    { timeout: 60_000 },
  );

  const resetResult = await evaluateWithTransientRetry(
    page,
    () => window.__URDF_STUDIO_DEBUG__.resetFixtureFiles(),
  );
  if (!resetResult?.ok) {
    throw new Error(`Could not reset fixture files: ${JSON.stringify(resetResult)}`);
  }

  const seedResult = await evaluateWithTransientRetry(
    page,
    (file) => window.__URDF_STUDIO_DEBUG__.seedFixtureFile(file),
    {
      addFileContent: true,
      content: model.content,
      format: 'urdf',
      name: model.file,
    },
  );
  if (!seedResult?.ok) {
    throw new Error(`Could not seed fixture file ${model.file}: ${JSON.stringify(seedResult)}`);
  }

  await evaluateWithTransientRetry(page, (fileName) => {
    const api = window.__URDF_STUDIO_DEBUG__;
    window.__transformerControllerLoad = {
      error: null,
      requested: fileName,
    };
    void api
      .loadRobotByName(fileName)
      .then((result) => {
        window.__transformerControllerLoad = {
          error: null,
          requested: fileName,
          result,
        };
      })
      .catch((error) => {
        window.__transformerControllerLoad = {
          error: error instanceof Error ? error.message : String(error),
          requested: fileName,
        };
      });
  }, model.file);

  await waitForReady(page);

  await page.waitForFunction(
    () => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
      return (
        Object.keys(snapshot?.store?.links ?? {}).length > 0 &&
        Object.keys(snapshot?.store?.joints ?? {}).length > 0
      );
    },
    { timeout: 30000 },
  );

  const loadProbe = await evaluateWithTransientRetry(page, (fileName) => {
    const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
    const load = window.__transformerControllerLoad ?? null;
    return {
      error: load?.error ?? null,
      jointCount: Object.keys(snapshot?.store?.joints ?? {}).length,
      linkCount: Object.keys(snapshot?.store?.links ?? {}).length,
      selectedFile: snapshot?.selectedFile?.name ?? null,
      targetFile: fileName,
    };
  }, model.file);
  if (loadProbe.error || loadProbe.linkCount <= 0 || loadProbe.jointCount <= 0) {
    throw new Error(`Could not load seeded model: ${JSON.stringify(loadProbe)}`);
  }
}

async function getGizmoSummary(page) {
  return page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getTransformGizmoSummary?.() ?? []);
}

async function waitForRuntimeCollisionReady(page, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;

  while (Date.now() < deadline) {
    last = await page.evaluate(() => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const snapshot = api?.getRegressionSnapshot?.() ?? null;
      const runtime = snapshot?.runtime ?? null;
      const projectedCollisionTargets = (api?.getProjectedInteractionTargets?.() ?? [])
        .filter((target) =>
          target?.type === 'link' &&
          target?.subType === 'collision' &&
          target?.targetKind === 'geometry');

      return {
        runtimeLinkCount: Number(runtime?.linkCount ?? 0),
        runtimeCollisionGroupCount: Number(runtime?.collisionGroupCount ?? 0),
        projectedCollisionTargetCount: projectedCollisionTargets.length,
      };
    });

    if (
      last.runtimeLinkCount > 0 &&
      last.runtimeCollisionGroupCount > 0 &&
      last.projectedCollisionTargetCount > 0
    ) {
      return last;
    }

    await delay(200);
  }

  throw new Error(`Timed out waiting for runtime collision scene; last state: ${JSON.stringify(last)}`);
}

async function getBestEditableCollisionTarget(page) {
  const targets = await getProjectedInteractionTargets(page, {
    type: 'link',
    subType: 'collision',
    targetKind: 'geometry',
  });

  const resolved = await page.evaluate((nextTargets) => {
    const projection = window.__URDF_STUDIO_DEBUG__?.__workspaceStore__
      ?.getState?.()
      ?.getSceneProjection?.();
    const resolveLink = (identity) => {
      if (!identity) return null;
      let globalId = identity;
      let ref = projection?.globalToEntityRef?.get(globalId) ?? null;
      if (ref?.type === 'link') return { globalId, ref };
      globalId = Object.entries(projection?.robotData?.links ?? {}).find(
        ([id, link]) => id === identity || link?.id === identity || link?.name === identity,
      )?.[0];
      ref = globalId ? projection?.globalToEntityRef?.get(globalId) ?? null : null;
      return ref?.type === 'link' ? { globalId, ref } : null;
    };

    for (const target of nextTargets) {
      const resolvedLink =
        resolveLink(target?.linkId) ??
        resolveLink(target?.id) ??
        resolveLink(target?.sourceName);
      if (resolvedLink) {
        return {
          ...target,
          id: resolvedLink.globalId,
          componentId: resolvedLink.ref.componentId,
          entityId: resolvedLink.ref.entityId,
          objectIndex: target?.objectIndex ?? 0,
        };
      }
    }

    return null;
  }, targets);

  return resolved ?? null;
}

async function getBestEditableOriginTarget(page) {
  const targets = await getProjectedInteractionTargets(page, {
    helperKind: 'origin-axes',
    targetKind: 'helper',
  });

  return page.evaluate((projectedTargets) => {
    const state = window.__URDF_STUDIO_DEBUG__?.__workspaceStore__?.getState?.() ?? null;
    const projection = state?.getSceneProjection?.();
    const resolveLink = (identity) => {
      if (!identity) return null;
      let globalId = identity;
      let ref = projection?.globalToEntityRef?.get(globalId) ?? null;
      if (ref?.type === 'link') return { globalId, ref };
      globalId = Object.entries(projection?.robotData?.links ?? {}).find(
        ([id, link]) => id === identity || link?.id === identity || link?.name === identity,
      )?.[0];
      ref = globalId ? projection?.globalToEntityRef?.get(globalId) ?? null : null;
      return ref?.type === 'link' ? { globalId, ref } : null;
    };

    for (const target of projectedTargets) {
      const link = resolveLink(target?.id ?? target?.linkId ?? target?.sourceName);
      if (!link) {
        continue;
      }

      const component = state?.workspace?.components?.[link.ref.componentId] ?? null;
      const parentJoint = Object.entries(component?.robot?.joints ?? {}).find(
        ([, joint]) => joint?.childLinkId === link.ref.entityId,
      );
      if (!parentJoint) {
        continue;
      }

      return {
        jointId: parentJoint[0],
        linkId: link.globalId,
        componentId: link.ref.componentId,
        entityId: link.ref.entityId,
        projected: target,
      };
    }

    return null;
  }, targets);
}

async function waitForEditableOriginTarget(page, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;

  while (Date.now() < deadline) {
    try {
      last = await getBestEditableOriginTarget(page);
      if (last) return last;
    } catch (error) {
      if (!isTransientPageContextError(error)) {
        throw error;
      }
    }
    await delay(150);
  }

  const fallback = await evaluateWithTransientRetry(page, () => {
    const state = window.__URDF_STUDIO_DEBUG__?.__workspaceStore__?.getState?.() ?? null;
    const projection = state?.getSceneProjection?.();
    for (const component of Object.values(state?.workspace?.components ?? {})) {
      for (const [jointId, joint] of Object.entries(component?.robot?.joints ?? {})) {
        const entityId = joint?.childLinkId ?? null;
        if (!entityId || entityId === component?.robot?.rootLinkId) continue;
        const globalEntry = [...(projection?.globalToEntityRef?.entries?.() ?? [])].find(
          ([, ref]) => ref?.type === 'link' &&
            ref.componentId === component.id && ref.entityId === entityId,
        );
        if (!globalEntry) continue;
        return {
          jointId,
          linkId: globalEntry[0],
          componentId: component.id,
          entityId,
          projected: null,
        };
      }
    }

    return null;
  });
  if (fallback) return fallback;

  throw new Error(`Timed out waiting for editable origin target; last: ${JSON.stringify(last)}`);
}

async function selectCollisionTarget(page, target) {
  const result = await evaluateWithTransientRetry(page, (nextTarget) => {
    const selectionStore = window.__URDF_STUDIO_DEBUG__?.__selectionStore__?.getState?.();
    if (!selectionStore?.setSelection) return { ok: false };
    selectionStore.setInteractionGuard?.(null);
    selectionStore.setSelection({
      entity: {
        type: 'link',
        componentId: nextTarget.componentId,
        entityId: nextTarget.entityId,
      },
      subType: 'collision',
      objectIndex: nextTarget.objectIndex ?? 0,
    });
    return {
      ok: true,
      selection: window.__URDF_STUDIO_DEBUG__?.__selectionStore__?.getState?.()?.selection ?? null,
    };
  }, target);
  if (result?.ok) {
    await page.waitForFunction(
      (expectedId) => {
        const selection =
          window.__URDF_STUDIO_DEBUG__?.__selectionStore__?.getState?.()?.selection ?? null;
        const projection = window.__URDF_STUDIO_DEBUG__?.__workspaceStore__
          ?.getState?.()
          ?.getSceneProjection?.();
        return selection?.entity?.type === 'link' &&
          projection?.globalToEntityRef?.get(expectedId)?.componentId ===
            selection.entity.componentId &&
          projection?.globalToEntityRef?.get(expectedId)?.entityId === selection.entity.entityId;
      },
      { timeout: 5000 },
      target.id,
    );
  }
  return result;
}

async function selectOriginTarget(page, target) {
  const result = await evaluateWithTransientRetry(page, (nextTarget) => {
    const selectionStore = window.__URDF_STUDIO_DEBUG__?.__selectionStore__?.getState?.();
    if (!selectionStore?.setSelection) return { ok: false };
    selectionStore.setInteractionGuard?.(null);
    selectionStore.setSelection({
      entity: {
        type: 'link',
        componentId: nextTarget.componentId,
        entityId: nextTarget.entityId,
      },
      helperKind: 'origin-axes',
    });
    return {
      ok: true,
      selection: window.__URDF_STUDIO_DEBUG__?.__selectionStore__?.getState?.()?.selection ?? null,
    };
  }, target);
  if (result?.ok) {
    await page.waitForFunction(
      (expectedId) => {
        const selection =
          window.__URDF_STUDIO_DEBUG__?.__selectionStore__?.getState?.()?.selection ?? null;
        return (
          selection?.entity?.type === 'link' &&
          window.__URDF_STUDIO_DEBUG__?.__workspaceStore__
            ?.getState?.()
            ?.getSceneProjection?.()
            ?.globalToEntityRef?.get(expectedId)?.componentId ===
              selection.entity.componentId &&
          selection?.helperKind === 'origin-axes'
        );
      },
      { timeout: 5000 },
      target.linkId,
    );
  }
  return result;
}

async function setTransformMode(page, mode) {
  const result = await store.setViewerToolMode(page, mode);
  if (!result?.ok) {
    throw new Error(`Could not switch transform mode to ${mode}: ${JSON.stringify(result)}`);
  }
  await delay(350);
}

async function waitForGizmoEntry(page, predicate, label, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  let last = [];

  while (Date.now() < deadline) {
    try {
      last = await getGizmoSummary(page);
    } catch (error) {
      if (!isTransientPageContextError(error)) {
        throw error;
      }
      await delay(100);
      continue;
    }
    const match = last.find(predicate);
    if (match) return match;
    await delay(100);
  }

  throw new Error(`Timed out waiting for ${label}; last gizmo summary: ${JSON.stringify(last)}`);
}

async function moveToPointAndGetGizmoSummary(page, point) {
  await page.mouse.move(point.clientX, point.clientY);
  await delay(180);
  return getGizmoSummary(page);
}

async function zoomCanvas(page) {
  const point = await page.evaluate(() => {
    const canvas = [...document.querySelectorAll('canvas')]
      .map((entry) => {
        const rect = entry.getBoundingClientRect();
        return {
          height: rect.height,
          left: rect.left,
          top: rect.top,
          visible: rect.width > 0 && rect.height > 0,
          width: rect.width,
        };
      })
      .find((entry) => entry.visible);
    if (!canvas) return null;
    return {
      clientX: canvas.left + canvas.width * 0.25,
      clientY: canvas.top + canvas.height * 0.25,
    };
  });
  if (!point) throw new Error('Could not locate a visible canvas for zoom regression.');

  await page.mouse.move(point.clientX, point.clientY);
  for (let index = 0; index < ZOOM_WHEEL_STEPS; index += 1) {
    await page.mouse.wheel({ deltaY: ZOOM_WHEEL_DELTA_Y });
    await delay(120);
  }
  await delay(450);
}

function hasKind(summary, kind) {
  return summary.some((entry) => entry.kind === kind);
}

async function main() {
  const suite = createTestSuite('Transformer Controller Gizmo');
  const session = await createSession();
  const { page } = session;
  const report = {};

  try {
    await seedAndLoadModel(page, MODEL);

    await store.setViewerFlags(page, {
      showOrigins: true,
      showOriginsOverlay: true,
      originSize: 1,
    });

    const originTarget = await waitForEditableOriginTarget(page);
    assert(suite, Boolean(originTarget), 'editable origin target is available');

    await setTransformMode(page, 'rotate');
    const originSelectionResult = await selectOriginTarget(page, originTarget);
    assert(suite, originSelectionResult.ok, 'origin helper selection is applied through debug store');
    await delay(250);

    const originFrontArc = await waitForGizmoEntry(
      page,
      (entry) => entry.kind === 'rotate-front-arc',
      'origin rotate front arc',
    );
    assert(
      suite,
      originFrontArc.worldRadius <= ORIGIN_ROTATE_FRONT_ARC_WORLD_RADIUS_MAX,
      `origin front arc remains locally scaled (${originFrontArc.worldRadius.toFixed(3)}m)`,
    );

    const originERing = await waitForGizmoEntry(
      page,
      (entry) => entry.kind === 'rotate-e-ring',
      'origin rotate E ring',
    );
    assert(
      suite,
      originERing.worldRadius <= ORIGIN_ROTATE_E_RING_WORLD_RADIUS_MAX,
      `origin E ring remains locally scaled (${originERing.worldRadius.toFixed(3)}m)`,
    );

    await store.setViewerFlags(page, {
      showCollision: true,
      showCollisionAlwaysOnTop: true,
      highlightMode: 'collision',
    });
    await store.setViewerToolMode(page, 'select');
    report.runtime = await waitForRuntimeCollisionReady(page);

    const target = await getBestEditableCollisionTarget(page);
    assert(suite, Boolean(target), 'projected collision target is available');

    const selectionResult = await selectCollisionTarget(page, target);
    assert(suite, selectionResult.ok, 'collision target selection is applied through debug store');
    await delay(250);

    await setTransformMode(page, 'universal');
    const universalArrow = await waitForGizmoEntry(
      page,
      (entry) => entry.kind === 'translate-arrow',
      'universal translate arrow',
    );
    const universalArc = await waitForGizmoEntry(
      page,
      (entry) =>
        entry.kind === 'rotate-front-arc' &&
        Number.isFinite(entry.clientX) &&
        Number.isFinite(entry.clientY),
      'universal rotate arc',
    );
    const universalSummary = await getGizmoSummary(page);
    assert(suite, !hasKind(universalSummary, 'translate-center'), 'universal mode hides translate center');
    assert(suite, !hasKind(universalSummary, 'rotate-e-ring'), 'universal mode hides E outer ring');
    assert(suite, !hasKind(universalSummary, 'rotate-trackball'), 'universal mode hides trackball');
    assert(
      suite,
      universalSummary.filter((entry) => entry.kind === 'rotate-front-arc').length > 0,
      'universal mode shows axis rotate arcs',
    );
    assert(suite, !universalSummary.some((entry) => entry.kind?.includes('knob')), 'rotate knobs are removed');

    assert(suite, Number.isFinite(universalArrow.clientX), 'universal translate arrow is projected');
    assert(suite, Number.isFinite(universalArc.clientX), 'universal rotate arc is projected');

    await selectCollisionTarget(page, target);
    await delay(250);
    await setTransformMode(page, 'translate');
    await waitForGizmoEntry(
      page,
      (entry) => entry.kind === 'translate-arrow',
      'translate arrow',
    );
    const xyPlane = await waitForGizmoEntry(
      page,
      (entry) => entry.kind === 'translate-plane-xy',
      'XY translate plane',
    );
    const translateSummary = await getGizmoSummary(page);
    for (const kind of ['translate-plane-xy', 'translate-plane-yz', 'translate-plane-xz']) {
      assert(suite, hasKind(translateSummary, kind), `${kind} is present in translate mode`);
    }
    assert(suite, hasKind(translateSummary, 'translate-center'), 'translate mode shows center point');
    assertGreaterThan(
      suite,
      translateSummary.filter((entry) => entry.kind === 'translate-arrow').length,
      0,
      'translate arrows remain present',
    );
    assert(suite, Number.isFinite(xyPlane.clientX), 'XY translate plane is projected');

    await selectCollisionTarget(page, target);
    await delay(250);
    await setTransformMode(page, 'rotate');
    const rotateSummary = await getGizmoSummary(page);
    assert(
      suite,
      rotateSummary.filter((entry) => entry.kind === 'rotate-front-arc').length === 3,
      'three bright front arcs are present in rotate mode',
    );
    assert(
      suite,
      rotateSummary.filter((entry) => entry.kind === 'rotate-guide-ring').length === 3,
      'three faded full guide rings are present in rotate mode',
    );
    assert(suite, hasKind(rotateSummary, 'rotate-e-ring'), 'rotate mode shows E outer ring');
    assert(suite, hasKind(rotateSummary, 'rotate-trackball'), 'rotate mode shows trackball');
    assert(suite, !rotateSummary.some((entry) => entry.kind?.includes('knob')), 'rotate mode has no knobs');

    const frontArc = await waitForGizmoEntry(
      page,
      (entry) =>
        entry.kind === 'rotate-front-arc' &&
        Number.isFinite(entry.clientX) &&
        Number.isFinite(entry.clientY),
      'front rotate arc',
    );
    const hoverSummary = await moveToPointAndGetGizmoSummary(page, frontArc);
    assert(
      suite,
      hoverSummary.some(
        (entry) =>
          entry.kind === 'rotate-front-arc' &&
          entry.axis === frontArc.axis &&
          entry.active === true,
      ),
      'hovering the front rotate arc activates the arc visual',
    );

    await zoomCanvas(page);
    const zoomedFrontArc = await waitForGizmoEntry(
      page,
      (entry) => entry.kind === 'rotate-front-arc' && entry.axis === frontArc.axis,
      'zoomed front rotate arc',
    );
    const worldRadiusDelta = relativeDelta(frontArc.worldRadius, zoomedFrontArc.worldRadius);
    const screenRadiusDelta = relativeDelta(frontArc.screenRadius, zoomedFrontArc.screenRadius);
    assert(
      suite,
      worldRadiusDelta <= WORLD_RADIUS_STABLE_RELATIVE_EPSILON,
      `front arc world radius stays fixed across zoom (${(worldRadiusDelta * 100).toFixed(2)}%)`,
    );
    assert(
      suite,
      screenRadiusDelta >= SCREEN_RADIUS_CHANGE_RELATIVE_MIN,
      `front arc screen radius changes across zoom (${(screenRadiusDelta * 100).toFixed(2)}%)`,
    );

    report.browserErrors = session.errors();
    assertNoBrowserErrors(suite, session, 'transformer controller gizmo flow');
    report.gizmo = {
      frontArcAxis: frontArc.axis,
      originFrontArcWorldRadius: originFrontArc.worldRadius,
      originERingWorldRadius: originERing.worldRadius,
      screenRadiusDelta,
      universalKinds: universalSummary.map((entry) => entry.kind),
      worldRadiusDelta,
    };
  } finally {
    await session.cleanup();
  }

  await writeReport('transformer_controller_gizmo', report);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
