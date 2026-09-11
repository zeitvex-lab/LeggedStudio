import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

test('shared collision overlay material helpers expose normalized overlay defaults', async () => {
    let moduleUnderTest: null | typeof import('./collisionOverlayMaterial.ts') = null;

    try {
        moduleUnderTest = await import('./collisionOverlayMaterial.ts');
    } catch {
        moduleUnderTest = null;
    }

    assert.ok(moduleUnderTest, 'expected shared collision overlay material helper module');

    const { COLLISION_OVERLAY_RENDER_ORDER, collisionBaseMaterial, configureCollisionOverlayMaterial, createCollisionOverlayMaterial } = moduleUnderTest;

    assert.equal(COLLISION_OVERLAY_RENDER_ORDER, 999);

    const configuredMaterial = configureCollisionOverlayMaterial(new THREE.MeshBasicMaterial({ color: 0xff0000 }));
    assert.equal(configuredMaterial.transparent, true);
    assert.equal(configuredMaterial.depthWrite, false);
    assert.equal(configuredMaterial.depthTest, false);
    assert.equal(configuredMaterial.polygonOffset, true);
    assert.equal(configuredMaterial.polygonOffsetFactor, -1);
    assert.equal(configuredMaterial.polygonOffsetUnits, -4);
    assert.equal(configuredMaterial.userData.isCollisionMaterial, true);

    const createdMaterial = createCollisionOverlayMaterial('shared_collision_test');
    assert.equal(createdMaterial instanceof THREE.MeshStandardMaterial, true);
    assert.equal(createdMaterial.name, 'shared_collision_test');
    assert.equal(createdMaterial.transparent, true);
    assert.equal(createdMaterial.opacity, 0.35);
    assert.equal(createdMaterial.depthWrite, false);
    assert.equal(createdMaterial.depthTest, false);
    assert.equal(createdMaterial.userData.isCollisionMaterial, true);

    assert.equal(collisionBaseMaterial.transparent, true);
    assert.equal(collisionBaseMaterial.depthWrite, false);
    assert.equal(collisionBaseMaterial.depthTest, false);
    assert.equal(collisionBaseMaterial.userData.isCollisionMaterial, true);
    assert.equal(collisionBaseMaterial.userData.isSharedMaterial, true);
});
