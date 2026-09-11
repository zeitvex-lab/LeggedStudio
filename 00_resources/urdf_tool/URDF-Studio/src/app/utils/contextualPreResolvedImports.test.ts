import test from 'node:test';
import assert from 'node:assert/strict';

import { ensureWorkerXmlDomApis } from '@/core/utils/ensureWorkerXmlDomApis';
import type { RobotFile } from '@/types';
import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { disposeRobotImportWorker } from '@/app/hooks/robotImportWorkerBridge';
import {
  buildContextualPreResolvedImports,
  shouldBuildContextualPreResolvedImports,
} from './contextualPreResolvedImports';

ensureWorkerXmlDomApis(globalThis as typeof globalThis);

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

function restoreGlobalProperty<T extends keyof typeof globalThis>(
  key: T,
  originalValue: (typeof globalThis)[T] | undefined,
) {
  if (originalValue === undefined) {
    delete globalThis[key];
    return;
  }

  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value: originalValue,
  });
}

function installRobotImportWorkerMock() {
  const originalWorker = globalThis.Worker;
  let resolveRequestCount = 0;

  class FakeRobotImportWorker {
    private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

    private readonly contextSnapshots = new Map<string, {
      availableFiles?: RobotFile[];
      assets?: Record<string, string>;
      allFileContents?: Record<string, string>;
    }>();

    addEventListener(type: string, handler: WorkerEventHandler): void {
      const handlers = this.listeners.get(type) ?? new Set<WorkerEventHandler>();
      handlers.add(handler);
      this.listeners.set(type, handlers);
    }

    removeEventListener(type: string, handler: WorkerEventHandler): void {
      this.listeners.get(type)?.delete(handler);
    }

    postMessage(message: any): void {
      if (message?.type === 'sync-context') {
        this.contextSnapshots.set(message.contextId, message.context ?? {});
        return;
      }

      if (message?.type !== 'resolve-robot-file') {
        return;
      }

      resolveRequestCount += 1;
      const context = message.contextId
        ? this.contextSnapshots.get(message.contextId)
        : undefined;
      const options = {
        ...context,
        ...message.options,
        availableFiles: message.options?.availableFiles ?? context?.availableFiles,
        assets: message.options?.assets ?? context?.assets,
        allFileContents: message.options?.allFileContents ?? context?.allFileContents,
      };

      queueMicrotask(() => {
        const result = resolveRobotFileData(message.file, options);
        this.listeners.get('message')?.forEach((handler) => {
          handler({
            data: {
              type: 'resolve-robot-file-result',
              requestId: message.requestId,
              result,
            },
          });
        });
      });
    }

    terminate(): void {}
  }

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: FakeRobotImportWorker as unknown as typeof Worker,
  });

  return {
    get resolveRequestCount() {
      return resolveRequestCount;
    },
    restore() {
      disposeRobotImportWorker();
      restoreGlobalProperty('Worker', originalWorker);
    },
  };
}

test('buildContextualPreResolvedImports pre-resolves xacro files with imported includes', async () => {
  const workerMock = installRobotImportWorkerMock();
  const robotFiles: RobotFile[] = [
    {
      name: 'demo/xacro/robot.xacro',
      format: 'xacro',
      content: `<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="demo_xacro">
  <xacro:include filename="parts/link.xacro" />
</robot>`,
    },
    {
      name: 'demo/xacro/parts/link.xacro',
      format: 'xacro',
      content: `<robot name="included_links">
  <gazebo>
    <plugin filename="libgazebo_ros_control.so" name="gazebo_ros_control" />
  </gazebo>
  <link name="base_link" />
</robot>`,
    },
  ];

  try {
    const result = await buildContextualPreResolvedImports(robotFiles, {
      availableFiles: robotFiles,
      allFileContents: {},
      assets: {},
    });

    assert.equal(result.length, 1);
    const rootEntry = result.find((entry) => entry.fileName === 'demo/xacro/robot.xacro');
    assert.ok(rootEntry, 'Expected root xacro entry to be pre-resolved');
    assert.equal(rootEntry?.result.status, 'ready');
    if (!rootEntry || rootEntry.result.status !== 'ready') {
      assert.fail('Expected root xacro result to be ready');
    }
    assert.equal(rootEntry.result.robotData.name, 'demo_xacro');
    assert.equal(rootEntry.result.robotData.rootLinkId, 'base_link');
    assert.equal(rootEntry.result.resolvedUrdfSourceFilePath, 'demo/xacro/robot.xacro');
  } finally {
    workerMock.restore();
  }
});

test('buildContextualPreResolvedImports ignores non-xacro files', async () => {
  const workerMock = installRobotImportWorkerMock();
  const robotFiles: RobotFile[] = [
    {
      name: 'demo/robot.urdf',
      format: 'urdf',
      content: '<robot name="demo"><link name="base_link" /></robot>',
    },
  ];

  try {
    const result = await buildContextualPreResolvedImports(robotFiles, {
      availableFiles: robotFiles,
      allFileContents: {},
      assets: {},
    });

    assert.deepEqual(result, []);
  } finally {
    workerMock.restore();
  }
});

test('buildContextualPreResolvedImports pre-resolves an explicit URDF preferred file with deferred asset paths', async () => {
  const workerMock = installRobotImportWorkerMock();
  const robotFiles: RobotFile[] = [
    {
      name: 'pr2_description/urdf/pr2_simplified.urdf',
      format: 'urdf',
      content: `<robot name="pr2">
  <link name="base_link">
    <visual>
      <geometry>
        <mesh filename="package://drake/examples/pr2/models/pr2_description/meshes/base_v0/base.stl" />
      </geometry>
    </visual>
  </link>
</robot>`,
    },
  ];

  try {
    const result = await buildContextualPreResolvedImports(
      robotFiles,
      {
        availableFiles: robotFiles,
        allFileContents: {},
        assets: {
          'pr2_description/meshes/base_v0/base.stl': 'deferred-asset-path-hint',
        },
      },
      {
        preferredFileName: 'pr2_description/urdf/pr2_simplified.urdf',
      },
    );

    assert.equal(result.length, 1);
    assert.equal(result[0]?.fileName, 'pr2_description/urdf/pr2_simplified.urdf');
    assert.equal(result[0]?.format, 'urdf');
    assert.equal(result[0]?.result.status, 'ready');
    if (result[0]?.result.status !== 'ready') {
      assert.fail('Expected preferred URDF result to be ready');
    }
    assert.equal(
      result[0].result.robotData.links.base_link?.visual.meshPath,
      'pr2_description/meshes/base_v0/base.stl',
    );
  } finally {
    workerMock.restore();
  }
});

test('buildContextualPreResolvedImports resolves xacro context through the import worker path when Worker is available', async () => {
  const workerMock = installRobotImportWorkerMock();

  const robotFiles: RobotFile[] = [
    {
      name: 'demo/xacro/robot.xacro',
      format: 'xacro',
      content: `<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="demo_xacro">
  <xacro:include filename="parts/link.xacro" />
</robot>`,
    },
    {
      name: 'demo/xacro/parts/link.xacro',
      format: 'xacro',
      content: `<robot name="included_links">
  <link name="base_link" />
</robot>`,
    },
  ];

  try {
    const result = await buildContextualPreResolvedImports(robotFiles, {
      availableFiles: robotFiles,
      allFileContents: {},
      assets: {},
    });

    assert.equal(workerMock.resolveRequestCount, 1);
    assert.equal(result.length, 1);
    assert.equal(result[0]?.result.status, 'ready');
  } finally {
    workerMock.restore();
  }
});

test('shouldBuildContextualPreResolvedImports only enables contextual reparsing when pre-import context exists', () => {
  assert.equal(shouldBuildContextualPreResolvedImports({
    availableFiles: [],
    allFileContents: {},
    assets: {},
  }), false);

  assert.equal(shouldBuildContextualPreResolvedImports({
    availableFiles: [{
      name: 'demo/robot.urdf',
      format: 'urdf',
      content: '<robot name="demo"><link name="base_link" /></robot>',
    }],
    allFileContents: {},
    assets: {},
  }), true);

  assert.equal(shouldBuildContextualPreResolvedImports({
    availableFiles: [],
    allFileContents: { 'demo/materials/test.material': 'material Demo {}' },
    assets: {},
  }), true);

  assert.equal(shouldBuildContextualPreResolvedImports({
    availableFiles: [],
    allFileContents: {},
    assets: { 'demo/meshes/base.stl': 'solid demo' },
  }), true);
});
