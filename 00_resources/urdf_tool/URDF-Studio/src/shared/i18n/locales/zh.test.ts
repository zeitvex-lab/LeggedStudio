import assert from 'node:assert/strict';
import test from 'node:test';

import { zh } from './zh.ts';
import { zhWorkflow } from './zhWorkflow.ts';

test('advanced mode product copy stays consistent in Chinese', () => {
  assert.equal(zh.proMode, '高级模式');
  assert.match(zh.generateWorkspaceUrdfConfirmMessage, /高级模式/);
  assert.match(zh.generateWorkspaceUrdfDisconnected, /高级模式/);
  assert.match(zh.exportProjectWorkspaceSummaryDesc, /高级模式/);
  assert.match(zh.disconnectedWorkspaceUrdfExportMessage, /高级模式/);
  assert.doesNotMatch(zh.exportProjectWorkspaceSummaryDesc, /专业模式/);
});

test('Chinese locale keeps workflow copy from the workflow source of truth', () => {
  for (const key of Object.keys(zhWorkflow) as Array<keyof typeof zhWorkflow>) {
    assert.equal(zh[key], zhWorkflow[key], `workflow key drifted: ${String(key)}`);
  }
});
