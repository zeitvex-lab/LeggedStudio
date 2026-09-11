import assert from 'node:assert/strict';
import test from 'node:test';

import type { ExportProgressState } from '@/features/file-io';

import {
  createExportProgressReporter,
  replaceTemplate,
  trimProgressFileLabel,
} from './progress.ts';

test('replaceTemplate substitutes all placeholders', () => {
  assert.equal(
    replaceTemplate('Export {name} has {count} files. {name} is ready.', {
      name: 'robot',
      count: 3,
    }),
    'Export robot has 3 files. robot is ready.',
  );
});

test('trimProgressFileLabel keeps the last two path segments', () => {
  assert.equal(trimProgressFileLabel('/tmp/exports/robot/root.usd'), 'robot/root.usd');
  assert.equal(trimProgressFileLabel('root.usd'), 'root.usd');
  assert.equal(trimProgressFileLabel(''), '');
});

test('createExportProgressReporter computes normalized progress updates', () => {
  const updates: ExportProgressState[] = [];
  const reportProgress = createExportProgressReporter((progress) => {
    updates.push(progress);
  }, 4);

  reportProgress(1, 'Preparing', 'Start', { stageProgress: 0.5, indeterminate: false });
  reportProgress(2, 'Generating', 'Continue', { stageProgress: 0.25, indeterminate: false });

  assert.equal(updates.length, 2);
  assert.deepEqual(updates[0], {
    stepLabel: 'Preparing',
    detail: 'Start',
    progress: 0.125,
    currentStep: 1,
    totalSteps: 4,
    indeterminate: false,
  });
  assert.deepEqual(updates[1], {
    stepLabel: 'Generating',
    detail: 'Continue',
    progress: 0.3125,
    currentStep: 2,
    totalSteps: 4,
    indeterminate: false,
  });
});
