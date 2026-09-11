import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildUnifiedViewerRetainedRobotScopeKey,
  shouldReuseUnifiedViewerRetainedRobot,
} from './unifiedViewerRetainedRobot.ts';

test('buildUnifiedViewerRetainedRobotScopeKey keeps non-USD viewer scopes stable', () => {
  assert.equal(
    buildUnifiedViewerRetainedRobotScopeKey({
      sourceFile: { format: 'urdf', name: 'robots/go2.urdf' },
    }),
    'urdf:robots/go2.urdf',
  );

  assert.equal(
    buildUnifiedViewerRetainedRobotScopeKey({
      sourceFilePath: 'workspace/generated.robot',
      sourceFormat: 'mjcf',
    }),
    'mjcf:workspace/generated.robot',
  );

  assert.equal(
    buildUnifiedViewerRetainedRobotScopeKey({
      sourceFormat: 'sdf',
    }),
    'sdf:__inline__',
  );
});

test('buildUnifiedViewerRetainedRobotScopeKey disables retained reuse for USD scenes', () => {
  assert.equal(
    buildUnifiedViewerRetainedRobotScopeKey({
      sourceFile: { format: 'usd', name: 'robots/go2.usd' },
    }),
    null,
  );
});

test('shouldReuseUnifiedViewerRetainedRobot only keeps same-scope robots alive', () => {
  assert.equal(
    shouldReuseUnifiedViewerRetainedRobot('urdf:robots/go2.urdf', 'urdf:robots/go2.urdf'),
    true,
  );
  assert.equal(
    shouldReuseUnifiedViewerRetainedRobot('urdf:robots/go2.urdf', 'urdf:robots/g1.urdf'),
    false,
  );
  assert.equal(shouldReuseUnifiedViewerRetainedRobot('urdf:robots/go2.urdf', null), false);
});
