import test from 'node:test';
import assert from 'node:assert/strict';

import {
  SNAPSHOT_MIN_LONG_EDGE,
  clampSnapshotRenderPlanToPixelBudget,
  resolveSnapshotRenderTargetSamples,
  resolveSnapshotRenderPlan,
  resolveSnapshotTiledRenderPlan,
} from './snapshotResolution.ts';

test('resolveSnapshotRenderPlan keeps native size when the drawing buffer already meets the target', () => {
  assert.deepEqual(
    resolveSnapshotRenderPlan({
      baseWidth: 4200,
      baseHeight: 2363,
      basePixelRatio: 2,
      maxRenderbufferSize: 8192,
      maxTextureSize: 8192,
    }),
    {
      baseWidth: 4200,
      baseHeight: 2363,
      basePixelRatio: 2,
      scale: 1,
      targetWidth: 4200,
      targetHeight: 2363,
      targetPixelRatio: 2,
    },
  );
});

test('resolveSnapshotRenderPlan raises the render scale up to the snapshot long-edge floor', () => {
  const plan = resolveSnapshotRenderPlan({
    baseWidth: 1680,
    baseHeight: 945,
    basePixelRatio: 1.75,
    maxRenderbufferSize: 8192,
    maxTextureSize: 16384,
  });

  assert.equal(plan.targetWidth, SNAPSHOT_MIN_LONG_EDGE);
  assert.equal(plan.targetHeight, 2160);
  assert.equal(plan.scale, SNAPSHOT_MIN_LONG_EDGE / 1680);
  assert.equal(plan.targetPixelRatio, 4);
});

test('resolveSnapshotRenderPlan respects GPU limits instead of oversizing the capture', () => {
  const plan = resolveSnapshotRenderPlan({
    baseWidth: 1920,
    baseHeight: 1080,
    basePixelRatio: 2,
    maxRenderbufferSize: 3000,
    maxTextureSize: 4096,
  });

  assert.equal(plan.targetWidth, 3000);
  assert.equal(plan.targetHeight, 1688);
  assert.equal(plan.targetPixelRatio, 3.125);
});

test('resolveSnapshotRenderPlan honors an explicit long-edge target when provided', () => {
  const plan = resolveSnapshotRenderPlan({
    baseWidth: 3840,
    baseHeight: 2160,
    basePixelRatio: 2,
    targetLongEdge: 2560,
    maxRenderbufferSize: 8192,
    maxTextureSize: 8192,
  });

  assert.equal(plan.targetWidth, 2560);
  assert.equal(plan.targetHeight, 1440);
  assert.equal(plan.scale, 2560 / 3840);
  assert.equal(plan.targetPixelRatio, (2560 / 3840) * 2);
});

test('clampSnapshotRenderPlanToPixelBudget preserves aspect ratio while shrinking unsafe captures', () => {
  const plan = clampSnapshotRenderPlanToPixelBudget(
    {
      baseWidth: 3840,
      baseHeight: 2160,
      basePixelRatio: 2,
      scale: 2,
      targetWidth: 7680,
      targetHeight: 4320,
      targetPixelRatio: 4,
    },
    16_000_000,
  );

  assert.equal(plan.targetWidth, 5333);
  assert.equal(plan.targetHeight, 3000);
  assert.equal(plan.scale, 5333 / 3840);
  assert.equal(plan.targetPixelRatio, 2 * (5333 / 3840));
});

test('resolveSnapshotRenderTargetSamples disables MSAA for very large renders', () => {
  assert.equal(
    resolveSnapshotRenderTargetSamples({
      width: 7680,
      height: 4320,
      requestedSamples: 8,
      maxSupportedSamples: 8,
    }),
    0,
  );
});

test('resolveSnapshotRenderTargetSamples keeps moderate MSAA on medium-size renders', () => {
  assert.equal(
    resolveSnapshotRenderTargetSamples({
      width: 3840,
      height: 2160,
      requestedSamples: 8,
      maxSupportedSamples: 8,
    }),
    4,
  );
});

test('resolveSnapshotTiledRenderPlan preserves full supersampled coverage within tile budgets', () => {
  const plan = resolveSnapshotTiledRenderPlan({
    outputWidth: 7680,
    outputHeight: 4320,
    supersampleScale: 4,
    maxRenderbufferSize: 16384,
    maxTextureSize: 16384,
    tileInternalPixelBudget: 10_000_000,
  });

  assert.equal(plan.fullRenderWidth, 30_720);
  assert.equal(plan.fullRenderHeight, 17_280);
  assert.ok(plan.tiles.length > 1);
  assert.equal(plan.tiles[0]?.outputX, 0);
  assert.equal(plan.tiles[0]?.outputY, 0);
  assert.equal(plan.tiles.at(-1)!.outputX + plan.tiles.at(-1)!.outputWidth, 7680);
  assert.equal(plan.tiles.at(-1)!.outputY + plan.tiles.at(-1)!.outputHeight, 4320);
  assert.equal(plan.tiles.at(-1)!.renderX + plan.tiles.at(-1)!.renderWidth, 30_720);
  assert.equal(plan.tiles.at(-1)!.renderY + plan.tiles.at(-1)!.renderHeight, 17_280);
  assert.ok(
    plan.tiles.every((tile) => tile.renderWidth * tile.renderHeight <= 10_000_000),
  );
});

test('resolveSnapshotTiledRenderPlan respects small render target caps', () => {
  const plan = resolveSnapshotTiledRenderPlan({
    outputWidth: 3840,
    outputHeight: 2160,
    supersampleScale: 4,
    maxRenderbufferSize: 2048,
    maxTextureSize: 4096,
    tileInternalPixelBudget: 10_000_000,
  });

  assert.ok(plan.tiles.length > 1);
  assert.ok(plan.tiles.every((tile) => tile.renderWidth <= 2048));
  assert.ok(plan.tiles.every((tile) => tile.renderHeight <= 2048));
});
