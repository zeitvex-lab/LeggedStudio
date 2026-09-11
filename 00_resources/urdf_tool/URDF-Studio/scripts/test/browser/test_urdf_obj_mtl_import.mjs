#!/usr/bin/env node

/**
 * URDF OBJ+MTL browser regression.
 *
 * Generates a small URDF package where the URDF references an OBJ mesh and the
 * OBJ references an MTL file derived from an existing textured DAE fixture. The
 * test imports the package as a zip and verifies that the MTL and texture
 * sidecars are registered and used by the runtime mesh.
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

import {
  createSession,
  createTestSuite,
  assert,
  assertGreaterThan,
  waitForReady,
  getMaterialSnapshot,
  getCanvasDiagnostics,
  writeReport,
  printSummary,
  assertNoBrowserErrors,
} from './helpers/base-helpers.mjs';
import { importZippedModel } from './helpers/zip-import-helpers.mjs';

const CARDBOARD_DAE_PATH = path.resolve(
  'test/gazebo_models/cardboard_box/meshes/cardboard_box.dae',
);
const CARDBOARD_TEXTURE_ROOT = path.resolve(
  'test/gazebo_models/cardboard_box/materials/textures',
);
const EXPECTED_TEXTURE_SUFFIX = 'materials/textures/cardboard_box.png';

async function readCardboardDaeMaterial() {
  const daeContent = await fs.readFile(CARDBOARD_DAE_PATH, 'utf8');
  const materialName =
    daeContent.match(/<material\b[^>]*\bname=["']([^"']+)["'][^>]*>/i)?.[1] ??
    'CardboardBoxes';
  const textureFileName =
    daeContent.match(/<library_images\b[\s\S]*?<init_from>\s*([^<]+?)\s*<\/init_from>/i)?.[1] ??
    'cardboard_box.png';

  return { materialName, textureFileName };
}

async function writeFixture(rootDir) {
  const daeMaterial = await readCardboardDaeMaterial();

  await fs.rm(rootDir, { recursive: true, force: true });
  await fs.mkdir(path.join(rootDir, 'meshes'), { recursive: true });
  await fs.mkdir(path.join(rootDir, 'materials', 'textures'), { recursive: true });
  await fs.copyFile(
    path.join(CARDBOARD_TEXTURE_ROOT, daeMaterial.textureFileName),
    path.join(rootDir, 'materials', 'textures', daeMaterial.textureFileName),
  );

  await fs.writeFile(
    path.join(rootDir, 'robot.urdf'),
    [
      '<?xml version="1.0"?>',
      '<robot name="obj_mtl_regression">',
      '  <link name="base_link">',
      '    <visual>',
      '      <geometry>',
      '        <mesh filename="meshes/body.obj"/>',
      '      </geometry>',
      '    </visual>',
      '  </link>',
      '</robot>',
      '',
    ].join('\n'),
  );

  await fs.writeFile(
    path.join(rootDir, 'meshes', 'body.obj'),
    [
      'mtllib body.mtl',
      'o Body',
      `usemtl ${daeMaterial.materialName}`,
      'v -0.25 -0.25 -0.25',
      'v 0.25 -0.25 -0.25',
      'v 0.25 0.25 -0.25',
      'v -0.25 0.25 -0.25',
      'v -0.25 -0.25 0.25',
      'v 0.25 -0.25 0.25',
      'v 0.25 0.25 0.25',
      'v -0.25 0.25 0.25',
      'vt 0 0',
      'vt 1 0',
      'vt 1 1',
      'vt 0 1',
      'f 1/1 2/2 3/3',
      'f 1/1 3/3 4/4',
      'f 5/1 8/4 7/3',
      'f 5/1 7/3 6/2',
      'f 1/1 5/2 6/3',
      'f 1/1 6/3 2/4',
      'f 2/1 6/2 7/3',
      'f 2/1 7/3 3/4',
      'f 3/1 7/2 8/3',
      'f 3/1 8/3 4/4',
      'f 4/1 8/2 5/3',
      'f 4/1 5/3 1/4',
      '',
    ].join('\n'),
  );

  await fs.writeFile(
    path.join(rootDir, 'meshes', 'body.mtl'),
    [
      `newmtl ${daeMaterial.materialName}`,
      'Ka 0.588 0.588 0.588',
      'Kd 1.0 1.0 1.0',
      'Ks 0.0 0.0 0.0',
      'Ns 10',
      'd 1.0',
      'illum 2',
      `map_Kd ../materials/textures/${daeMaterial.textureFileName}`,
      '',
    ].join('\n'),
  );

  return daeMaterial;
}

function hasExpectedRuntimeTexture(snapshot) {
  return snapshot.runtimeVisualMeshes.some((mesh) =>
    mesh.effectiveVisible !== false &&
    !mesh.isPlaceholder &&
    mesh.textureCount > 0);
}

async function waitForRuntimeTexturedMaterial(page, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let lastSnapshot = null;

  while (Date.now() < deadline) {
    lastSnapshot = await getMaterialSnapshot(page);
    if (hasExpectedRuntimeTexture(lastSnapshot)) {
      return lastSnapshot;
    }
    await delay(250);
  }

  throw new Error(
    `Timed out waiting for runtime MTL texture: ${JSON.stringify(lastSnapshot)}`,
  );
}

async function getAssetDebugState(page) {
  return page.evaluate(() => window.__URDF_STUDIO_DEBUG__?.getAssetDebugState?.() ?? null);
}

function includesPathEnding(paths, suffix) {
  return Array.isArray(paths) &&
    paths.some((entry) => String(entry).replace(/\\/g, '/').endsWith(suffix));
}

async function main() {
  const suite = createTestSuite('URDF OBJ MTL Import');
  const session = await createSession();
  const fixtureDir = path.resolve(
    `tmp/regression/urdf_obj_mtl_fixture_${process.pid}_${Date.now()}`,
  );
  const results = {};

  try {
    const daeMaterial = await writeFixture(fixtureDir);

    const loadedName = await importZippedModel(
      session.page,
      fixtureDir,
      'robot.urdf',
      90_000,
      'urdf_obj_mtl',
    );
    await waitForReady(session.page, 120_000);

    const materialSnapshot = await waitForRuntimeTexturedMaterial(session.page);
    const assetDebugState = await getAssetDebugState(session.page);
    const canvas = await getCanvasDiagnostics(session.page);

    assert(suite, loadedName.endsWith('robot.urdf'), 'zip import loaded the generated URDF');
    assertGreaterThan(
      suite,
      materialSnapshot.runtimeVisualMeshCount,
      0,
      `runtime visual meshes present (${materialSnapshot.runtimeVisualMeshCount})`,
    );
    assertGreaterThan(
      suite,
      materialSnapshot.runtimeTextureCount,
      0,
      `runtime MTL textures present (${materialSnapshot.runtimeTextureCount})`,
    );
    assert(
      suite,
      hasExpectedRuntimeTexture(materialSnapshot),
      'runtime mesh keeps DAE-derived MTL texture',
    );
    assert(
      suite,
      materialSnapshot.runtimeVisualMeshes.every((mesh) => !mesh.isPlaceholder),
      'runtime visual meshes are real meshes, not placeholders',
    );
    assert(
      suite,
      includesPathEnding(assetDebugState?.appAssetKeys, 'meshes/body.obj'),
      'app asset scope includes archived OBJ',
    );
    assert(
      suite,
      includesPathEnding(assetDebugState?.appAssetKeys, 'meshes/body.mtl'),
      'app asset scope includes archived MTL',
    );
    assert(
      suite,
      includesPathEnding(assetDebugState?.appAssetKeys, EXPECTED_TEXTURE_SUFFIX),
      'app asset scope includes archived MTL texture',
    );
    assert(
      suite,
      includesPathEnding(assetDebugState?.viewerScopedAssetKeys, 'meshes/body.mtl'),
      'viewer asset scope includes archived MTL',
    );
    assert(
      suite,
      includesPathEnding(assetDebugState?.viewerScopedAssetKeys, EXPECTED_TEXTURE_SUFFIX),
      'viewer asset scope includes archived MTL texture',
    );
    assert(suite, canvas.usable, 'primary canvas is usable');
    assertNoBrowserErrors(suite, session, 'URDF OBJ MTL import');

    Object.assign(results, {
      loadedName,
      daeMaterial,
      sourceDae: CARDBOARD_DAE_PATH,
      materialSnapshot,
      assetDebugState,
      canvas,
    });
  } catch (error) {
    try {
      results.materialSnapshot = await getMaterialSnapshot(session.page);
      results.assetDebugState = await getAssetDebugState(session.page);
      results.canvas = await getCanvasDiagnostics(session.page);
    } catch {}
    assert(suite, false, `URDF OBJ MTL import completed - ${error.message}`);
    results.error = error.message;
  } finally {
    await session.cleanup();
    await fs.rm(fixtureDir, { recursive: true, force: true });
  }

  await writeReport('urdf_obj_mtl_import', results);
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
