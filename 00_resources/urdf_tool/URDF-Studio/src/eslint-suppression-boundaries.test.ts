import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

type SuppressionBaseline = Record<string, Record<string, { count: number }>>;

const repoRoot = process.cwd();
const suppressionBudgets = {
  '@typescript-eslint/no-explicit-any': 705,
  '@typescript-eslint/no-unused-vars': 109,
  'react-hooks/exhaustive-deps': 69,
} as const;

function readSuppressionBaseline(): SuppressionBaseline {
  return JSON.parse(
    readFileSync(path.join(repoRoot, 'eslint-suppressions.json'), 'utf8'),
  ) as SuppressionBaseline;
}

test('eslint suppression baseline does not grow without an explicit budget update', () => {
  const baseline = readSuppressionBaseline();
  const totals = new Map<string, number>();

  Object.values(baseline).forEach((rules) => {
    Object.entries(rules).forEach(([ruleName, suppression]) => {
      totals.set(ruleName, (totals.get(ruleName) ?? 0) + suppression.count);
    });
  });

  Object.entries(suppressionBudgets).forEach(([ruleName, budget]) => {
    const actual = totals.get(ruleName) ?? 0;
    assert.ok(actual <= budget, `${ruleName} suppressions grew from ${budget} to ${actual}`);
  });
});

test('typed runtime boundary files stay out of the eslint suppression baseline', () => {
  const baseline = readSuppressionBaseline();
  const typedBoundaryFiles = [
    'src/features/urdf-viewer/renderers/types.ts',
    'src/features/urdf-viewer/renderers/loadedRobotSceneSync.ts',
    'src/shared/components/3d/runtimeGeometrySelection.ts',
    'src/shared/components/3d/runtimeRobotTypes.ts',
    'src/shared/debug/regressionState.ts',
    'src/shared/utils/jointTypes.ts',
    'src/shared/utils/threeBounds.ts',
  ];

  typedBoundaryFiles.forEach((filePath) => {
    assert.equal(baseline[filePath], undefined, `${filePath} should not need lint suppressions`);
  });
});
