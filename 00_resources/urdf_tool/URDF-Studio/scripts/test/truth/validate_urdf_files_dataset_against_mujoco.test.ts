import assert from 'node:assert/strict';
import test from 'node:test';

import {
  compareGeometrySection,
  detectSectionMisclassifications,
  hasComparableMujocoContent,
  type GeometryFact,
  type MujocoGeomFact,
} from './validate_urdf_files_dataset_against_mujoco.ts';

const compareOptions = {
  positionTolerance: 1e-6,
  rotationTolerance: 1e-6,
  scaleTolerance: 1e-6,
};

function studioGeometry(section: 'visual' | 'collision'): GeometryFact {
  return {
    dimensions: [1, 2, 3],
    index: 0,
    linkName: 'base_link',
    pos: [0.1, 0.2, 0.3],
    quatWxyz: [1, 0, 0, 0],
    section,
    type: 'box',
  };
}

function mujocoGeometry(section: 'visual' | 'collision'): MujocoGeomFact {
  return {
    bodyName: 'base_link',
    conaffinity: section === 'visual' ? 0 : 1,
    contype: section === 'visual' ? 0 : 1,
    dimensions: [1, 2, 3],
    group: section === 'visual' ? 1 : 0,
    id: 0,
    meshId: null,
    meshName: null,
    name: null,
    pos: [0.1, 0.2, 0.3],
    quatWxyz: [1, 0, 0, 0],
    section,
    size: [0.5, 1, 1.5],
    type: 'box',
  };
}

function compileResult(overrides: Record<string, unknown> = {}) {
  return {
    bodies: [],
    counts: {
      nbody: 1,
      ngeom: 0,
      njnt: 0,
      nmesh: 0,
      nq: 0,
      nu: 0,
      nv: 0,
    },
    error: null,
    geoms: [],
    joints: [],
    mode: 'collision',
    ok: true,
    ...overrides,
  };
}

test('detectSectionMisclassifications reports visual geometry compiled as collision', () => {
  const issues = detectSectionMisclassifications(
    [studioGeometry('visual')],
    [],
    [],
    [mujocoGeometry('collision')],
    compareOptions,
  );

  assert.equal(issues.length, 1);
  assert.equal(issues[0]?.kind, 'section_mismatch');
  assert.equal(issues[0]?.expected, 'visual');
  assert.equal(issues[0]?.actual, 'collision');
});

test('detectSectionMisclassifications reports collision geometry compiled as visual', () => {
  const issues = detectSectionMisclassifications(
    [],
    [studioGeometry('collision')],
    [mujocoGeometry('visual')],
    [],
    compareOptions,
  );

  assert.equal(issues.length, 1);
  assert.equal(issues[0]?.kind, 'section_mismatch');
  assert.equal(issues[0]?.expected, 'collision');
  assert.equal(issues[0]?.actual, 'visual');
});

test('detectSectionMisclassifications ignores correctly classified geometry', () => {
  const issues = detectSectionMisclassifications(
    [studioGeometry('visual')],
    [studioGeometry('collision')],
    [mujocoGeometry('visual')],
    [mujocoGeometry('collision')],
    compareOptions,
  );

  assert.deepEqual(issues, []);
});

test('compareGeometrySection reports MuJoCo geometry missing from Studio import', () => {
  const issues = compareGeometrySection(
    [],
    [mujocoGeometry('visual')],
    'visual',
    compareOptions,
  );

  assert.equal(issues.length, 1);
  assert.equal(issues[0]?.kind, 'visual_count_mismatch');
  assert.equal(issues[0]?.expected, 1);
  assert.equal(issues[0]?.actual, 0);
});

test('hasComparableMujocoContent treats world-only compiles as non-comparable fragments', () => {
  assert.equal(
    hasComparableMujocoContent({
      collision: compileResult({ mode: 'collision' }),
      relativePath: 'robots/source_fragment.urdf',
      sourcePath: '/tmp/source_fragment.urdf',
      visual: compileResult({ mode: 'visual' }),
    }),
    false,
  );
});

test('hasComparableMujocoContent accepts any compiled body, geom, or joint content', () => {
  assert.equal(
    hasComparableMujocoContent({
      collision: compileResult({ mode: 'collision' }),
      relativePath: 'robots/model.urdf',
      sourcePath: '/tmp/model.urdf',
      visual: compileResult({
        counts: {
          nbody: 2,
          ngeom: 0,
          njnt: 0,
          nmesh: 0,
          nq: 0,
          nu: 0,
          nv: 0,
        },
        mode: 'visual',
      }),
    }),
    true,
  );
});
