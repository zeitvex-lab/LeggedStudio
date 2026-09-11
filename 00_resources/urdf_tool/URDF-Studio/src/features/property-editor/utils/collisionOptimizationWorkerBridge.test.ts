import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, type RobotData, type UrdfVisual } from '@/types';
import {
  createCollisionOptimizationWorkerClient,
} from './collisionOptimizationWorkerBridge.ts';
import { analyzeCollisionOptimizationInline } from './collisionOptimizationWorkerAnalysis.ts';
import type {
  CollisionOptimizationAnalysis,
  CollisionOptimizationSettings,
} from './collisionOptimization.ts';

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

class FakeWorker {
  private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

  public readonly postedMessages: unknown[] = [];

  public terminated = false;

  addEventListener(type: string, handler: WorkerEventHandler): void {
    const handlers = this.listeners.get(type) ?? new Set<WorkerEventHandler>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: WorkerEventHandler): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown): void {
    this.postedMessages.push(message);
  }

  terminate(): void {
    this.terminated = true;
  }

  emitMessage(message: unknown): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data: message });
    });
  }

  emitError(error: Error): void {
    this.listeners.get('error')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }

  emitMessageError(error: Error): void {
    this.listeners.get('messageerror')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }
}

function createGeometry(type: GeometryType, dimensions = { x: 0.1, y: 0.1, z: 1 }): UrdfVisual {
  return {
    type,
    dimensions,
    color: '#888888',
    origin: {
      xyz: { x: 0, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
  };
}

function createRobot(): RobotData {
  return {
    name: 'worker-test',
    links: {
      base: {
        id: 'base',
        name: 'base',
        visual: createGeometry(GeometryType.BOX),
        collision: createGeometry(GeometryType.BOX),
      },
    },
    joints: {},
    rootLinkId: 'base',
  };
}

function createSettings(): CollisionOptimizationSettings {
  return {
    scope: 'all',
    meshStrategy: 'smart',
    cylinderStrategy: 'keep',
    rodBoxStrategy: 'capsule',
    coaxialJointMergeStrategy: 'keep',
    avoidSiblingOverlap: false,
  };
}

function createAnalysis(): CollisionOptimizationAnalysis {
  return {
    targets: [],
    filteredTargets: [],
    candidates: [],
    meshAnalysisByTargetId: {},
  };
}

test('collision optimization worker client posts request ids and forwards progress', async () => {
  const fakeWorker = new FakeWorker();
  const client = createCollisionOptimizationWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });
  const progressEvents: unknown[] = [];
  const analysis = createAnalysis();

  const resultPromise = client.analyze({
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
    onProgress: (progress) => progressEvents.push(progress),
  });

  assert.equal(fakeWorker.postedMessages.length, 1);
  const request = fakeWorker.postedMessages[0] as { type: string; requestId: number };
  assert.equal(request.type, 'analyze');
  assert.equal(request.requestId, 1);

  fakeWorker.emitMessage({
    type: 'progress',
    requestId: request.requestId,
    stage: 'prepare-base',
    status: 'started',
  });
  fakeWorker.emitMessage({
    type: 'result',
    requestId: request.requestId,
    analysis,
  });

  assert.equal(await resultPromise, analysis);
  assert.deepEqual(progressEvents, [
    {
      requestId: 1,
      stage: 'prepare-base',
      status: 'started',
      completed: undefined,
      total: undefined,
    },
  ]);
});

test('collision optimization worker client cancels requests and ignores stale results', async () => {
  const fakeWorker = new FakeWorker();
  const client = createCollisionOptimizationWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });
  const controller = new AbortController();

  const resultPromise = client.analyze({
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
    signal: controller.signal,
  });

  const request = fakeWorker.postedMessages[0] as { requestId: number };
  controller.abort();

  await assert.rejects(
    resultPromise,
    (error) => error instanceof DOMException && error.name === 'AbortError',
  );
  assert.deepEqual(fakeWorker.postedMessages[1], {
    type: 'cancel',
    requestId: request.requestId,
  });

  fakeWorker.emitMessage({
    type: 'result',
    requestId: request.requestId,
    analysis: createAnalysis(),
  });
});

test('collision optimization worker client falls back inline when workers are unavailable', async () => {
  let inlineRequestId: number | null = null;
  const analysis = createAnalysis();
  const progressEvents: unknown[] = [];
  const client = createCollisionOptimizationWorkerClient({
    canUseWorker: () => false,
    runInlineAnalysis: async (args) => {
      inlineRequestId = args.requestId;
      args.onProgress?.({
        requestId: args.requestId,
        stage: 'finalizing',
        status: 'completed',
        completed: 1,
        total: 1,
      });
      return analysis;
    },
  });

  const result = await client.analyze({
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
    onProgress: (progress) => progressEvents.push(progress),
  });

  assert.equal(result, analysis);
  assert.equal(inlineRequestId, 1);
  assert.deepEqual(progressEvents, [
    {
      requestId: 1,
      stage: 'finalizing',
      status: 'completed',
      completed: 1,
      total: 1,
    },
  ]);
});

test('collision optimization worker client falls back inline after worker startup errors', async () => {
  const fakeWorker = new FakeWorker();
  const analysis = createAnalysis();
  let inlineCalled = false;
  const client = createCollisionOptimizationWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    runInlineAnalysis: async () => {
      inlineCalled = true;
      return analysis;
    },
  });

  const resultPromise = client.analyze({
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
  });

  fakeWorker.emitError(new Error('worker module failed to load'));

  assert.equal(await resultPromise, analysis);
  assert.equal(inlineCalled, true);
  assert.equal(fakeWorker.terminated, true);
});

test('collision optimization worker client falls back inline after request timeout', async () => {
  const fakeWorker = new FakeWorker();
  const analysis = createAnalysis();
  let inlineRequestId: number | null = null;
  const client = createCollisionOptimizationWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    requestTimeoutMs: 10,
    runInlineAnalysis: async (args) => {
      inlineRequestId = args.requestId;
      return analysis;
    },
  });

  const result = await client.analyze({
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
  });

  assert.equal(result, analysis);
  assert.equal(inlineRequestId, 1);
  assert.equal(fakeWorker.terminated, true);
});

test('collision optimization worker client falls back inline after message transfer failures', async () => {
  const fakeWorker = new FakeWorker();
  const analysis = createAnalysis();
  let inlineCalled = false;
  const client = createCollisionOptimizationWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    runInlineAnalysis: async () => {
      inlineCalled = true;
      return analysis;
    },
  });

  const resultPromise = client.analyze({
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
  });

  fakeWorker.emitMessageError(new Error('structured clone failed'));

  assert.equal(await resultPromise, analysis);
  assert.equal(inlineCalled, true);
  assert.equal(fakeWorker.terminated, true);
});

test('inline collision optimization analysis emits stage progress and builds candidates', async () => {
  const progressEvents: Array<{ stage: string; status: string }> = [];

  const analysis = await analyzeCollisionOptimizationInline({
    requestId: 42,
    source: { kind: 'robot', robot: createRobot() },
    assets: {},
    settings: createSettings(),
    onProgress: (progress) => {
      progressEvents.push({ stage: progress.stage, status: progress.status });
    },
  });

  assert.equal(analysis.targets.length, 1);
  assert.equal(analysis.filteredTargets.length, 1);
  assert.equal(analysis.candidates.length, 1);
  assert.deepEqual(
    progressEvents.filter((event) => event.status === 'started').map((event) => event.stage),
    ['prepare-base', 'mesh-analysis', 'clearance', 'candidates', 'finalizing'],
  );
});
