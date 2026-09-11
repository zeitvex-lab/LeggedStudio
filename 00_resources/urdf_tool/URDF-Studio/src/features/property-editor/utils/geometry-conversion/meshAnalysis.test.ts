import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveImportedAssetPath } from '@/core/parsers/meshPathUtils';

import { computeMeshAnalysisFromAssets } from './meshAnalysis.ts';

function createTextDataUrl(text: string): string {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(text)}`;
}

function createObjDataUrl(vertices: Array<[number, number, number]>): string {
  const objSource = ['o demo', ...vertices.map(([x, y, z]) => `v ${x} ${y} ${z}`), 'f 1 2 3'].join(
    '\n',
  );
  return createTextDataUrl(objSource);
}

test('computeMeshAnalysisFromAssets resolves short OBJ mesh paths against the USD source file path', async () => {
  const sourceFilePath = 'unitree_model/B2/usd/b2.viewer_roundtrip.usd';
  const meshPath = 'FR_calf_visual_0_section_0.obj';
  const resolvedMeshPath = resolveImportedAssetPath(meshPath, sourceFilePath);
  const distractorPath = 'other/package/with/deeper/path/FR_calf_visual_0_section_0.obj';
  const assets = {
    [distractorPath]: createObjDataUrl([
      [0, 0, 0],
      [2, 0, 0],
      [0, 0.5, 0],
    ]),
    [resolvedMeshPath]: createObjDataUrl([
      [0, 0, 0],
      [1, 0, 0],
      [0, 1, 0],
    ]),
  };

  const analysis = await (
    computeMeshAnalysisFromAssets as unknown as (
      meshPath: string,
      assets: Record<string, string>,
      meshScale: { x: number; y: number; z: number } | undefined,
      options: Record<string, never>,
      sourceFilePath: string,
    ) => Promise<{
      bounds: {
        x: number;
        y: number;
        z: number;
      };
    } | null>
  )(meshPath, assets, undefined, {}, sourceFilePath);

  assert.ok(analysis, 'expected mesh analysis to resolve the prepared USD mesh asset');
  assert.equal(analysis.bounds.x, 1);
  assert.equal(analysis.bounds.y, 1);
  assert.equal(analysis.bounds.z, 0);
});

test('computeMeshAnalysisFromAssets fails fast when an OBJ sidecar texture cannot resolve', async () => {
  const assets = {
    'robot/meshes/body.obj': createTextDataUrl(
      [
        'o demo',
        'v 0 0 0',
        'v 1 0 0',
        'v 0 1 0',
        'mtllib body.mtl',
        'usemtl default',
        'f 1 2 3',
      ].join('\n'),
    ),
    'robot/meshes/body.mtl': createTextDataUrl(['newmtl default', 'map_Kd missing.png'].join('\n')),
  };

  await assert.rejects(
    computeMeshAnalysisFromAssets('robot/meshes/body.obj', assets),
    /Asset lookup failed for "robot\/meshes\/missing\.png" under "robot\/meshes\/"/i,
  );
});
