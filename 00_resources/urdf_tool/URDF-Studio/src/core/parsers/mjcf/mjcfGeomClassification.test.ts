import test from 'node:test';
import assert from 'node:assert/strict';

import { assignMJCFBodyGeomRoles, classifyMJCFGeom } from './mjcfGeomClassification.ts';

test('classifies Apollo-style collision geoms as collision only', () => {
    const classification = classifyMJCFGeom({
        name: 'collision_capsule_body_pelvis',
        className: 'collision',
        classQName: 'collision',
        group: 3,
        contype: 0,
        conaffinity: 0,
    });

    assert.deepEqual(classification, { isVisual: false, isCollision: true });
});

test('classifies group 5 CollisionGeom names as collision only', () => {
    const classification = classifyMJCFGeom({
        name: 'wrLowerCollisionGeom_0',
        group: 5,
        contype: 0,
        conaffinity: 0,
    });

    assert.deepEqual(classification, { isVisual: false, isCollision: true });
});

test('keeps virtual helper geoms out of collision classification', () => {
    const classification = classifyMJCFGeom({
        name: 'virtual_pulley_geom',
        className: 'virtual_pulley',
        classQName: 'softfoot/virtual_pulley',
        group: 4,
        contype: 0,
        conaffinity: 0,
    });

    assert.deepEqual(classification, { isVisual: true, isCollision: false });
});

test('keeps inertial and fluid helper geoms out of render and collision roles', () => {
    assert.deepEqual(
        classifyMJCFGeom({
            name: 'wing_left_inertial',
            className: 'wing-inertial',
            classQName: 'body/wing/wing-inertial',
            group: 1,
            contype: 0,
            conaffinity: 0,
        }),
        { isVisual: false, isCollision: false },
    );

    assert.deepEqual(
        classifyMJCFGeom({
            name: 'wing_left_fluid',
            className: 'wing-fluid',
            classQName: 'body/wing/wing-fluid',
            group: 3,
            contype: 0,
            conaffinity: 0,
        }),
        { isVisual: false, isCollision: false },
    );
});

test('treats plain unclassified geoms as shared visual and collision geometry', () => {
    const classification = classifyMJCFGeom({
        name: 'torso',
        contype: 1,
        conaffinity: 1,
    });

    assert.deepEqual(classification, { isVisual: true, isCollision: true });
});

test('suppresses ambiguous shared geoms from visuals when body already has dedicated visual geometry', () => {
    const roles = assignMJCFBodyGeomRoles([
        {
            name: 'base_mesh',
            group: 1,
            contype: 0,
            conaffinity: 0,
        },
        {
            name: 'base_collision_box',
            contype: 1,
            conaffinity: 1,
        },
    ]);

    assert.deepEqual(
        roles.map(({ geom, renderVisual, renderCollision }) => ({
            name: geom.name,
            renderVisual,
            renderCollision,
        })),
        [
            { name: 'base_mesh', renderVisual: true, renderCollision: false },
            { name: 'base_collision_box', renderVisual: false, renderCollision: true },
        ],
    );
});
