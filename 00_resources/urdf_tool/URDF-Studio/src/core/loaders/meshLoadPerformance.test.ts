import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getMeshLoadPerformanceHistory,
  markPostMessageReceived,
  recordMeshLoadPerformance,
  type MeshLoadPerformanceEntry,
} from './meshLoadPerformance.ts';

type MeshLoadPerformanceTestGlobal = typeof globalThis & {
  __URDF_STUDIO_MESH_LOAD_PERFORMANCE__?: MeshLoadPerformanceEntry;
  __URDF_STUDIO_MESH_LOAD_PERFORMANCE_HISTORY__?: MeshLoadPerformanceEntry[];
  location?: { search?: string };
};

function installLocationSearch(search: string): () => void {
  const hadLocation = Object.prototype.hasOwnProperty.call(globalThis, 'location');
  const previousLocation = (globalThis as MeshLoadPerformanceTestGlobal).location;
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    value: { search },
  });

  return () => {
    if (hadLocation) {
      Object.defineProperty(globalThis, 'location', {
        configurable: true,
        value: previousLocation,
      });
      return;
    }

    delete (globalThis as Partial<MeshLoadPerformanceTestGlobal>).location;
  };
}

function clearMeshLoadPerformanceGlobals(): void {
  delete (globalThis as MeshLoadPerformanceTestGlobal).__URDF_STUDIO_MESH_LOAD_PERFORMANCE__;
  delete (globalThis as MeshLoadPerformanceTestGlobal)
    .__URDF_STUDIO_MESH_LOAD_PERFORMANCE_HISTORY__;
}

test('recordMeshLoadPerformance requires regressionDebug=1', () => {
  clearMeshLoadPerformanceGlobals();
  const restoreLocation = installLocationSearch('');
  try {
    recordMeshLoadPerformance({
      assetUrl: '/robot.obj',
      format: 'obj',
    });

    assert.equal(getMeshLoadPerformanceHistory().length, 0);
  } finally {
    restoreLocation();
    clearMeshLoadPerformanceGlobals();
  }
});

test('markPostMessageReceived records transfer and round-trip timings in debug mode', () => {
  clearMeshLoadPerformanceGlobals();
  const restoreLocation = installLocationSearch('?regressionDebug=1');
  try {
    const now = Date.now();
    const entry: MeshLoadPerformanceEntry = {
      assetUrl: '/robot.dae',
      format: 'collada',
      requestDispatchedAtEpochMs: now - 25,
      workerPostedAtEpochMs: now - 10,
    };

    markPostMessageReceived(entry);

    assert.ok((entry.postMessageTransferMs ?? 0) >= 0);
    assert.ok((entry.roundTripToMainMs ?? 0) >= (entry.postMessageTransferMs ?? 0));
    const history = getMeshLoadPerformanceHistory();
    assert.equal(history.length, 1);
    assert.equal(history[0]?.assetUrl, '/robot.dae');
    assert.equal(history[0]?.format, 'collada');
  } finally {
    restoreLocation();
    clearMeshLoadPerformanceGlobals();
  }
});
