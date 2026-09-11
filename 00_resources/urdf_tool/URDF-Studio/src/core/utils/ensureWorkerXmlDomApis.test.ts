import test from 'node:test';
import assert from 'node:assert/strict';

import { ensureWorkerXmlDomApis } from './ensureWorkerXmlDomApis';

test('ensureWorkerXmlDomApis installs worker XML and image polyfills', async () => {
  const scope = {} as typeof globalThis;

  ensureWorkerXmlDomApis(scope);

  assert.equal(typeof scope.DOMParser, 'function');
  assert.equal(typeof scope.XMLSerializer, 'function');
  assert.equal(typeof scope.document?.createElementNS, 'function');
  assert.equal(typeof scope.HTMLImageElement, 'function');
  assert.equal(typeof scope.Image, 'function');

  const image = scope.document!.createElementNS(
    'http://www.w3.org/1999/xhtml',
    'img',
  ) as unknown as {
    addEventListener: (type: 'load', listener: () => void) => void;
    complete: boolean;
    src: string;
  };

  const ImageElementCtor = scope.HTMLImageElement as unknown as new () => object;
  const ImageCtor = scope.Image as unknown as new () => object;

  assert.ok(image instanceof ImageElementCtor);
  assert.ok(new ImageCtor() instanceof ImageElementCtor);

  let didLoad = false;
  image.addEventListener('load', () => {
    didLoad = true;
  });
  image.src = 'textures/checker.png';

  await new Promise<void>((resolve) => {
    queueMicrotask(() => {
      resolve();
    });
  });

  assert.equal(image.complete, true);
  assert.equal(didLoad, true);
});
