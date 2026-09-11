import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveDeferredUsdSceneSnapshotDelayMs } from './deferredUsdSceneSnapshot.ts';

test('resolveDeferredUsdSceneSnapshotDelayMs waits out the initial ready grace period', () => {
  assert.equal(
    resolveDeferredUsdSceneSnapshotDelayMs({
      requestedAt: 1_000,
      now: 1_250,
      lastInteractionAt: 0,
      initialDelayMs: 1_200,
      interactionIdleMs: 900,
      maxDelayMs: 10_000,
    }),
    950,
  );
});

test('resolveDeferredUsdSceneSnapshotDelayMs waits for interaction idle after the initial delay', () => {
  assert.equal(
    resolveDeferredUsdSceneSnapshotDelayMs({
      requestedAt: 1_000,
      now: 2_300,
      lastInteractionAt: 2_000,
      initialDelayMs: 1_200,
      interactionIdleMs: 900,
      maxDelayMs: 10_000,
    }),
    600,
  );
});

test('resolveDeferredUsdSceneSnapshotDelayMs keeps delaying during an active drag', () => {
  assert.equal(
    resolveDeferredUsdSceneSnapshotDelayMs({
      requestedAt: 1_000,
      now: 20_000,
      lastInteractionAt: 19_900,
      activeInteraction: true,
      initialDelayMs: 1_200,
      interactionIdleMs: 900,
      maxDelayMs: 10_000,
    }),
    900,
  );
});

test('resolveDeferredUsdSceneSnapshotDelayMs eventually publishes after passive pointer motion', () => {
  assert.equal(
    resolveDeferredUsdSceneSnapshotDelayMs({
      requestedAt: 1_000,
      now: 12_000,
      lastInteractionAt: 11_950,
      initialDelayMs: 1_200,
      interactionIdleMs: 900,
      maxDelayMs: 10_000,
    }),
    0,
  );
});
