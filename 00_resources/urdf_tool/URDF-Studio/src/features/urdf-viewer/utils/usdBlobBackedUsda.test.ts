import assert from 'node:assert/strict';
import test from 'node:test';
import {
  hasBlobBackedLargeUsdaInStageScope,
  isBlobBackedLargeUsdaPlaceholder,
} from './usdBlobBackedUsda.ts';

test('detects blob-backed empty USDA placeholders', () => {
  assert.equal(
    isBlobBackedLargeUsdaPlaceholder({
      name: 'g1_description/configuration/g1_23dof_base.usda',
      format: 'usd',
      content: '',
      blobUrl: 'blob:g1-base',
    }),
    true,
  );

  assert.equal(
    isBlobBackedLargeUsdaPlaceholder({
      name: 'g1_description/configuration/g1_23dof_base.usda',
      format: 'usd',
      content: '#usda 1.0',
      blobUrl: 'blob:g1-base',
    }),
    false,
  );
});

test('only reports blob-backed USDA placeholders that are in the selected stage scope', () => {
  assert.equal(
    hasBlobBackedLargeUsdaInStageScope(
      {
        name: 'g1_description/g1_23dof.usda',
        format: 'usd',
        content: '#usda 1.0\n(\n  subLayers = [@./configuration/g1_23dof_physics.usda@]\n)\n',
        blobUrl: 'blob:g1-root',
      },
      [
        {
          name: 'g1_description/configuration/g1_23dof_physics.usda',
          format: 'usd',
          content: '#usda 1.0\n(\n  subLayers = [@g1_23dof_base.usda@]\n)\n',
          blobUrl: 'blob:g1-physics',
        },
        {
          name: 'g1_description/configuration/g1_23dof_base.usda',
          format: 'usd',
          content: '',
          blobUrl: 'blob:g1-base',
        },
        {
          name: 'g1_description/configuration/g1_29dof_base.usda',
          format: 'usd',
          content: '',
          blobUrl: 'blob:g1-29-base',
        },
      ],
    ),
    true,
  );

  assert.equal(
    hasBlobBackedLargeUsdaInStageScope(
      {
        name: 'g1_description/g1_29dof.usda',
        format: 'usd',
        content:
          '#usda 1.0\ndef Xform "G1" (prepend references = @configuration/g1_29dof_base.usda@) {}',
        blobUrl: 'blob:g1-29-root',
      },
      [
        {
          name: 'g1_description/configuration/g1_29dof_base.usda',
          format: 'usd',
          content: '#usda 1.0',
          blobUrl: 'blob:g1-29-base',
        },
        {
          name: 'g1_description/configuration/g1_23dof_base.usda',
          format: 'usd',
          content: '',
          blobUrl: 'blob:g1-23-base',
        },
      ],
    ),
    false,
  );
});
