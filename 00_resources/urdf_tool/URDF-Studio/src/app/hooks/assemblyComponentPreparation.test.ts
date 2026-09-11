import assert from 'node:assert/strict';
import test from 'node:test';

import { buildAssemblyComponentPreparationOverlayState } from './assemblyComponentPreparation.ts';

const t = {
  addingAssemblyComponentToWorkspace: 'Adding component',
  groundingAssemblyComponent: 'Grounding component',
  loadingRobot: 'Loading robot',
  preparingAssemblyComponent: 'Preparing component',
};

test('buildAssemblyComponentPreparationOverlayState returns prepare stage state', () => {
  const state = buildAssemblyComponentPreparationOverlayState(
    { name: 'robots/demo/model.usd', format: 'usd', content: '' },
    'prepare',
    t,
  );

  assert.deepEqual(state, {
    label: 'Loading robot',
    detail: 'model.usd',
    progress: 0.36,
    statusLabel: '1/3',
    stageLabel: 'Preparing component',
  });
});

test('buildAssemblyComponentPreparationOverlayState returns ground stage state', () => {
  const state = buildAssemblyComponentPreparationOverlayState(
    { name: 'demo.urdf', format: 'urdf', content: '' },
    'ground',
    t,
  );

  assert.deepEqual(state, {
    label: 'Loading robot',
    detail: 'demo.urdf',
    progress: 0.92,
    statusLabel: '3/3',
    stageLabel: 'Grounding component',
  });
});
