import { strict as assert } from 'node:assert';
import test from 'node:test';

import { createImportPathCollisionMap, remapImportedPath } from './libraryImportPathCollisions';

test('import collision paths use shared library key normalization', () => {
  const pathMap = createImportPathCollisionMap(
    ['/robots//demo/../demo/model.urdf?cache=1'],
    [],
  );

  assert.equal(
    remapImportedPath('\\robots\\demo\\model.urdf?cache=2', pathMap),
    'robots/demo/model.urdf',
  );
});
