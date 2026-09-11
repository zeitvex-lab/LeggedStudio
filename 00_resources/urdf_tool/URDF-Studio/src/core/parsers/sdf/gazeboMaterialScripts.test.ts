import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveSdfIncludeSource } from './sdfIncludeResolution.ts';
import { resolveGazeboScriptMaterial } from './gazeboMaterialScripts.ts';

test('SDF includes and Gazebo material scripts normalize equivalent relative paths', () => {
  const sdf = '<sdf version="1.7"><model name="sensor" /></sdf>';
  const resolvedInclude = resolveSdfIncludeSource(
    'model://demo/./nested/../sensor',
    {
      'demo/sensor/model.sdf': sdf,
    },
    'worlds/main.sdf',
  );

  const material = resolveGazeboScriptMaterial({
    allFileContents: {
      'demo/materials/scripts/demo.material': `
        material Demo/Painted
        {
          technique
          {
            pass
            {
              texture_unit
              {
                texture ../textures/coat.png
              }
            }
          }
        }`,
    },
    scriptName: 'Demo/Painted',
    scriptUris: ['model://demo/./materials\\scripts/../scripts'],
    sourcePath: 'worlds/main.sdf',
  });

  assert.deepEqual(resolvedInclude, {
    path: 'demo/sensor/model.sdf',
    content: sdf,
  });
  assert.equal(material?.texture, 'demo/materials/textures/coat.png');
});

test('resolveGazeboScriptMaterial resolves texture paths relative to gazebo material script roots', () => {
  const material = resolveGazeboScriptMaterial({
    allFileContents: {
      'demo/materials/scripts/demo.material': `
        material Demo/Painted
        {
          technique
          {
            pass
            {
              texture_unit
              {
                texture ../textures/coat.png
              }
            }
          }
        }`,
    },
    scriptName: 'Demo/Painted',
    scriptUris: ['materials/scripts'],
    sourcePath: 'demo/model.sdf',
  });

  assert.deepEqual(material, {
    name: 'Demo/Painted',
    texture: 'demo/materials/textures/coat.png',
  });
});

test('resolveGazeboScriptMaterial extracts alpha_rejection as alphaTest', () => {
  const material = resolveGazeboScriptMaterial({
    allFileContents: {
      'demo/materials/scripts/demo.material': `
        material Demo/Leaves
        {
          technique
          {
            pass
            {
              alpha_rejection greater 128
              texture_unit
              {
                texture leaves.png
              }
            }
          }
        }`,
    },
    scriptName: 'Demo/Leaves',
    scriptUris: ['materials/scripts'],
    sourcePath: 'demo/model.sdf',
  });

  assert.deepEqual(material, {
    name: 'Demo/Leaves',
    texture: 'demo/materials/textures/leaves.png',
    alphaTest: 128 / 255,
  });
});

test('resolveGazeboScriptMaterial extracts multi-pass textures with passes array', () => {
  const material = resolveGazeboScriptMaterial({
    allFileContents: {
      'demo/materials/scripts/demo.material': `
        material Demo/Grass
        {
          technique
          {
            pass
            {
              diffuse 1.0 1.0 1.0 1.0
              texture_unit
              {
                texture field.png
              }
            }
            pass
            {
              scene_blend alpha_blend
              depth_write off
              lighting off
              texture_unit
              {
                texture lines.png
              }
            }
          }
        }`,
    },
    scriptName: 'Demo/Grass',
    scriptUris: ['materials/scripts'],
    sourcePath: 'demo/model.sdf',
  });

  assert.equal(material?.name, 'Demo/Grass');
  assert.equal(material?.texture, 'demo/materials/textures/field.png');
  assert.ok(material?.passes, 'should have passes for multi-pass materials');
  assert.equal(material!.passes!.length, 2);
  assert.equal(material!.passes![0].texture, 'demo/materials/textures/field.png');
  assert.equal(material!.passes![1].texture, 'demo/materials/textures/lines.png');
  assert.equal(material!.passes![1].sceneBlend, 'alpha_blend');
  assert.equal(material!.passes![1].depthWrite, false);
  assert.equal(material!.passes![1].lighting, false);
});
