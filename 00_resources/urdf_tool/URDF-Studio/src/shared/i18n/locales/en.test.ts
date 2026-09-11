import assert from 'node:assert/strict';
import test from 'node:test';

import { en } from './en.ts';
import { enWorkflow } from './enWorkflow.ts';

test('workspace product copy avoids mode split language in English', () => {
  assert.doesNotMatch(en.generateWorkspaceUrdfConfirmTitle, /\bAdvanced mode\b/);
  assert.doesNotMatch(en.generateWorkspaceUrdfConfirmMessage, /\bAdvanced mode\b/);
  assert.doesNotMatch(en.generateWorkspaceUrdfDisconnected, /\bAdvanced mode\b/);
  assert.doesNotMatch(en.exportProjectWorkspaceSummaryDesc, /\bAdvanced mode\b/);
  assert.doesNotMatch(en.disconnectedWorkspaceUrdfExportMessage, /\bAdvanced mode\b/);
  assert.match(en.exportProjectWorkspaceSummaryDesc, /\bworkspace\b/);
  assert.doesNotMatch(en.exportProjectWorkspaceSummaryDesc, /\b[Pp]ro mode\b/);
  assert.doesNotMatch(en.exportProjectWorkspaceSummaryDesc, /\bpro-mode\b/);
});

test('English locale keeps workflow copy from the workflow source of truth', () => {
  for (const key of Object.keys(enWorkflow) as Array<keyof typeof enWorkflow>) {
    assert.equal(en[key], enWorkflow[key], `workflow key drifted: ${String(key)}`);
  }
});
