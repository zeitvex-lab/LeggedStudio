import assert from 'node:assert/strict';
import test from 'node:test';

import {
  preserveDocumentLoadProgressForSameFile,
  resolveRuntimeRobotReadyDocumentLoadState,
  shouldReuseResolvedMjcfViewerRuntime,
  shouldCommitResolvedRobotSelection,
  shouldIgnoreViewerLoadRegressionAfterReadySameFile,
  shouldIgnoreStaleViewerDocumentLoadEvent,
} from './documentLoadFlow.ts';

test('shouldCommitResolvedRobotSelection only commits once the file can drive the viewer scene', () => {
  assert.equal(
    shouldCommitResolvedRobotSelection({
      status: 'ready',
    }),
    true,
  );

  assert.equal(
    shouldCommitResolvedRobotSelection({
      status: 'needs_hydration',
    }),
    true,
  );

  assert.equal(
    shouldCommitResolvedRobotSelection({
      status: 'error',
      reason: 'source_only_fragment',
    }),
    false,
  );

  assert.equal(
    shouldCommitResolvedRobotSelection({
      status: 'error',
      reason: 'parse_failed',
    }),
    false,
  );
});

test('shouldIgnoreStaleViewerDocumentLoadEvent ignores old scene progress while a different file is staged', () => {
  assert.equal(
    shouldIgnoreStaleViewerDocumentLoadEvent({
      isPreviewing: false,
      activeDocumentFileName: 'robots/current.urdf',
      documentLoadState: {
        status: 'loading',
        fileName: 'robots/next.urdf',
      },
    }),
    true,
  );

  assert.equal(
    shouldIgnoreStaleViewerDocumentLoadEvent({
      isPreviewing: false,
      activeDocumentFileName: 'robots/current.urdf',
      documentLoadState: {
        status: 'hydrating',
        fileName: 'robots/next.usd',
      },
    }),
    true,
  );

  assert.equal(
    shouldIgnoreStaleViewerDocumentLoadEvent({
      isPreviewing: false,
      activeDocumentFileName: 'robots/current.urdf',
      documentLoadState: {
        status: 'loading',
        fileName: 'robots/current.urdf',
      },
    }),
    false,
  );

  assert.equal(
    shouldIgnoreStaleViewerDocumentLoadEvent({
      isPreviewing: true,
      activeDocumentFileName: 'robots/current.urdf',
      documentLoadState: {
        status: 'loading',
        fileName: 'robots/next.urdf',
      },
    }),
    false,
  );

  assert.equal(
    shouldIgnoreStaleViewerDocumentLoadEvent({
      isPreviewing: false,
      activeDocumentFileName: null,
      documentLoadState: {
        status: 'loading',
        fileName: 'robots/next.urdf',
      },
    }),
    false,
  );

  assert.equal(
    shouldIgnoreStaleViewerDocumentLoadEvent({
      isPreviewing: false,
      activeDocumentFileName: 'robots/current.urdf',
      documentLoadState: {
        status: 'ready',
        fileName: 'robots/next.urdf',
      },
    }),
    false,
  );
});

test('preserveDocumentLoadProgressForSameFile keeps advanced same-file USD progress from regressing back to checking-path', () => {
  assert.deepEqual(
    preserveDocumentLoadProgressForSameFile({
      currentState: {
        status: 'loading',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'finalizing-scene',
        message: null,
        progressMode: 'indeterminate',
        progressPercent: 96,
        loadedCount: null,
        totalCount: null,
      },
      nextState: {
        status: 'loading',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'checking-path',
        message: null,
        progressPercent: null,
        loadedCount: null,
        totalCount: null,
      },
    }),
    {
      status: 'loading',
      fileName: 'robots/unitree/g1.usda',
      format: 'usd',
      phase: 'finalizing-scene',
      message: null,
      progressMode: 'indeterminate',
      progressPercent: 96,
      loadedCount: null,
      totalCount: null,
    },
  );
});

test('preserveDocumentLoadProgressForSameFile keeps advanced same-file robot import progress from regressing back to preparing-scene', () => {
  assert.deepEqual(
    preserveDocumentLoadProgressForSameFile({
      currentState: {
        status: 'loading',
        fileName: 'robots/demo/demo.urdf',
        format: 'urdf',
        phase: 'preparing-scene',
        message: 'Parsing URDF',
        progressMode: 'percent',
        progressPercent: 28,
        loadedCount: null,
        totalCount: null,
      },
      nextState: {
        status: 'loading',
        fileName: 'robots/demo/demo.urdf',
        format: 'urdf',
        phase: 'preparing-scene',
        message: null,
        progressPercent: null,
        loadedCount: null,
        totalCount: null,
      },
    }),
    {
      status: 'loading',
      fileName: 'robots/demo/demo.urdf',
      format: 'urdf',
      phase: 'preparing-scene',
      message: 'Parsing URDF',
      progressMode: 'percent',
      progressPercent: 28,
      loadedCount: null,
      totalCount: null,
    },
  );
});

test('preserveDocumentLoadProgressForSameFile leaves unrelated files unchanged', () => {
  assert.deepEqual(
    preserveDocumentLoadProgressForSameFile({
      currentState: {
        status: 'loading',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'finalizing-scene',
        message: null,
        progressPercent: 96,
        loadedCount: null,
        totalCount: null,
      },
      nextState: {
        status: 'loading',
        fileName: 'robots/unitree/h1.usda',
        format: 'usd',
        phase: 'checking-path',
        message: null,
        progressPercent: null,
        loadedCount: null,
        totalCount: null,
      },
    }),
    {
      status: 'loading',
      fileName: 'robots/unitree/h1.usda',
      format: 'usd',
      phase: 'checking-path',
      message: null,
      progressPercent: null,
      loadedCount: null,
      totalCount: null,
    },
  );
});

test('shouldIgnoreViewerLoadRegressionAfterReadySameFile ignores hidden same-file viewer reload progress after ready', () => {
  assert.equal(
    shouldIgnoreViewerLoadRegressionAfterReadySameFile({
      currentState: {
        status: 'ready',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'ready',
        message: null,
        progressPercent: 100,
        loadedCount: null,
        totalCount: null,
      },
      nextState: {
        status: 'loading',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'checking-path',
        message: null,
        progressPercent: 0,
        loadedCount: null,
        totalCount: null,
      },
    }),
    true,
  );

  assert.equal(
    shouldIgnoreViewerLoadRegressionAfterReadySameFile({
      currentState: {
        status: 'ready',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'ready',
        message: null,
        progressPercent: 100,
        loadedCount: null,
        totalCount: null,
      },
      nextState: {
        status: 'hydrating',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'initializing-renderer',
        message: 'Initializing USD driver...',
        progressPercent: 28,
        loadedCount: null,
        totalCount: null,
      },
    }),
    true,
  );

  assert.equal(
    shouldIgnoreViewerLoadRegressionAfterReadySameFile({
      currentState: {
        status: 'ready',
        fileName: 'robots/unitree/g1.usda',
        format: 'usd',
        phase: 'ready',
        message: null,
        progressPercent: 100,
        loadedCount: null,
        totalCount: null,
      },
      nextState: {
        status: 'loading',
        fileName: 'robots/unitree/h1.usda',
        format: 'usd',
        phase: 'checking-path',
        message: null,
        progressPercent: 0,
        loadedCount: null,
        totalCount: null,
      },
    }),
    false,
  );
});

test('resolveRuntimeRobotReadyDocumentLoadState marks same-file MJCF runtime loads as ready', () => {
  assert.deepEqual(
    resolveRuntimeRobotReadyDocumentLoadState({
      activeFile: {
        name: 'robots/demo/scene.xml',
        format: 'mjcf',
      },
      currentState: {
        status: 'loading',
        fileName: 'robots/demo/scene.xml',
        format: 'mjcf',
        error: null,
        phase: 'preparing-scene',
        message: null,
        progressMode: 'percent',
        progressPercent: 40,
        loadedCount: null,
        totalCount: null,
      },
    }),
    {
      status: 'ready',
      fileName: 'robots/demo/scene.xml',
      format: 'mjcf',
      error: null,
      phase: 'ready',
      message: null,
      progressMode: 'percent',
      progressPercent: 100,
      loadedCount: null,
      totalCount: null,
    },
  );
});

test('resolveRuntimeRobotReadyDocumentLoadState ignores USD and mismatched files', () => {
  assert.equal(
    resolveRuntimeRobotReadyDocumentLoadState({
      activeFile: {
        name: 'robots/demo/world.usd',
        format: 'usd',
      },
      currentState: {
        status: 'loading',
        fileName: 'robots/demo/world.usd',
        format: 'usd',
      },
    }),
    null,
  );

  assert.equal(
    resolveRuntimeRobotReadyDocumentLoadState({
      activeFile: {
        name: 'robots/demo/scene.xml',
        format: 'mjcf',
      },
      currentState: {
        status: 'loading',
        fileName: 'robots/demo/other.xml',
        format: 'mjcf',
      },
    }),
    null,
  );
});

test('shouldReuseResolvedMjcfViewerRuntime keeps the current runtime when MJCF wrappers resolve to the same effective source', () => {
  assert.equal(
    shouldReuseResolvedMjcfViewerRuntime({
      currentSelectedFile: {
        name: 'robots/demo/b2.xml',
        format: 'mjcf',
        content: '<mujoco model=\"b2\" />',
      },
      nextFile: {
        name: 'robots/demo/scene.xml',
        format: 'mjcf',
        content: '<mujoco><include file=\"b2.xml\" /></mujoco>',
      },
      currentResolvedSource: {
        effectiveFileName: 'robots/demo/b2.xml',
        content: '<mujoco model=\"b2\" />',
      },
      nextResolvedSource: {
        effectiveFileName: 'robots/demo/b2.xml',
        content: '<mujoco model=\"b2\" />',
      },
    }),
    true,
  );

  assert.equal(
    shouldReuseResolvedMjcfViewerRuntime({
      currentSelectedFile: {
        name: 'robots/demo/b2.xml',
        format: 'mjcf',
        content: '<mujoco model=\"b2\" />',
      },
      nextFile: {
        name: 'robots/demo/scene.xml',
        format: 'mjcf',
        content: '<mujoco><include file=\"b2.xml\" /></mujoco>',
      },
      currentResolvedSource: {
        effectiveFileName: 'robots/demo/b2.xml',
        content: '<mujoco model=\"b2\" />',
      },
      nextResolvedSource: {
        effectiveFileName: 'robots/demo/scene.xml',
        content: '<mujoco><include file=\"b2.xml\" /></mujoco>',
      },
    }),
    false,
  );
});
