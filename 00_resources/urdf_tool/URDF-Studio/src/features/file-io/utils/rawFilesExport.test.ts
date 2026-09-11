import test from 'node:test';
import assert from 'node:assert/strict';

import { collectRawFilesZip } from './rawFilesExport.ts';

test('collectRawFilesZip rejects when an asset blob cannot be fetched instead of skipping it', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () =>
    ({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    }) as Response) as typeof fetch;

  try {
    await assert.rejects(
      collectRawFilesZip({
        assets: {
          'meshes/base.stl': 'blob:http://localhost/base.stl',
        },
        availableFiles: [],
        allFileContents: {},
        selectedFile: null,
      }),
      /meshes\/base\.stl/i,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('collectRawFilesZip rejects when a non-blob asset URL cannot be fetched', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () => {
    throw new Error('remote asset exploded');
  }) as typeof fetch;

  try {
    await assert.rejects(
      collectRawFilesZip({
        assets: {
          'textures/body.png': 'https://example.com/body.png',
        },
        availableFiles: [],
        allFileContents: {},
        selectedFile: null,
      }),
      /textures\/body\.png/i,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('collectRawFilesZip rejects when a binary workspace file blob cannot be fetched', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () => {
    throw new Error('blob fetch exploded');
  }) as typeof fetch;

  try {
    await assert.rejects(
      collectRawFilesZip({
        assets: {},
        availableFiles: [
          {
            name: 'robots/demo.usd',
            format: 'usd',
            content: '',
            blobUrl: 'blob:http://localhost/demo.usd',
          },
        ],
        allFileContents: {},
        selectedFile: null,
      }),
      /robots\/demo\.usd/i,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
