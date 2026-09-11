import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import { applyTranslateDisplayPatches } from './translateDisplayPatches.ts';

const AXES = ['X', 'Y', 'Z'] as const;

const createAxisLine = (axis: (typeof AXES)[number], color: number) => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0], 3));
  const material = new THREE.LineBasicMaterial({ color });
  const line = new THREE.Line(geometry, material);
  line.name = axis;
  return line;
};

const createAxisPickerMesh = (axis: (typeof AXES)[number]) => {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(0.2, 0, 1, 4, 1, false),
    new THREE.MeshBasicMaterial({ visible: false }),
  );
  mesh.name = axis;
  if (axis === 'X') {
    mesh.position.set(0.6, 0, 0);
    mesh.rotation.set(0, 0, -Math.PI / 2);
  } else if (axis === 'Y') {
    mesh.position.set(0, 0.6, 0);
  } else {
    mesh.position.set(0, 0, 0.6);
    mesh.rotation.set(Math.PI / 2, 0, 0);
  }
  return mesh;
};

const createTranslateGroups = () => {
  const visibleGroup = new THREE.Group();
  visibleGroup.add(
    createAxisLine('X', 0xff0000),
    createAxisLine('Y', 0x00ff00),
    createAxisLine('Z', 0x0000ff),
  );

  const pickerGroup = new THREE.Group();
  pickerGroup.add(createAxisPickerMesh('X'), createAxisPickerMesh('Y'), createAxisPickerMesh('Z'));

  return {
    gizmo: { translate: visibleGroup },
    picker: { translate: pickerGroup },
  };
};

const getGeometryAxisCenter = (mesh: THREE.Mesh, axis: (typeof AXES)[number]) => {
  const geometry = mesh.geometry as THREE.BufferGeometry;
  geometry.computeBoundingBox();
  const center = geometry.boundingBox?.getCenter(new THREE.Vector3());
  return center?.[axis.toLowerCase() as 'x' | 'y' | 'z'] ?? 0;
};

test('applyTranslateDisplayPatches creates mirrored thick-primary tips and shafts for every axis', () => {
  const gizmo = createTranslateGroups();

  applyTranslateDisplayPatches(gizmo, 1, { leaveRingGap: false });

  const visibleTranslate = gizmo.gizmo.translate;
  const tips = visibleTranslate.children.filter(
    (node) => node.userData?.urdfTranslateTip,
  ) as THREE.Mesh[];
  const shafts = visibleTranslate.children.filter(
    (node) => node.userData?.urdfTranslateShaft,
  ) as THREE.Mesh[];
  const gapBridges = visibleTranslate.children.filter(
    (node) => node.userData?.urdfTranslateGapBridge,
  );

  assert.equal(tips.length, 6);
  assert.equal(shafts.length, 6);
  assert.equal(gapBridges.length, 0);

  for (const axis of AXES) {
    const axisTips = tips.filter((node) => node.userData?.urdfAxis === axis);
    const axisShafts = shafts.filter((node) => node.userData?.urdfAxis === axis);

    assert.equal(axisTips.length, 2, `${axis} should have positive and negative tips`);
    assert.equal(axisShafts.length, 2, `${axis} should have positive and negative shafts`);

    const tipCenters = axisTips.map((mesh) => getGeometryAxisCenter(mesh, axis));
    const shaftCenters = axisShafts.map((mesh) => getGeometryAxisCenter(mesh, axis));

    assert.ok(
      tipCenters.some((value) => value > 0),
      `${axis} should include a positive tip`,
    );
    assert.ok(
      tipCenters.some((value) => value < 0),
      `${axis} should include a negative tip`,
    );
    assert.ok(
      shaftCenters.some((value) => value > 0),
      `${axis} should include a positive shaft`,
    );
    assert.ok(
      shaftCenters.some((value) => value < 0),
      `${axis} should include a negative shaft`,
    );
  }
});

test('applyTranslateDisplayPatches mirrors universal-mode ring gaps on both sides of every axis', () => {
  const gizmo = createTranslateGroups();

  applyTranslateDisplayPatches(gizmo, 1, { leaveRingGap: true });

  const visibleTranslate = gizmo.gizmo.translate;
  const tips = visibleTranslate.children.filter((node) => node.userData?.urdfTranslateTip);
  const shafts = visibleTranslate.children.filter((node) => node.userData?.urdfTranslateShaft);
  const gapBridges = visibleTranslate.children.filter(
    (node) => node.userData?.urdfTranslateGapBridge,
  );

  assert.equal(tips.length, 6);
  assert.equal(shafts.length, 12);
  assert.equal(gapBridges.length, 18);

  for (const axis of AXES) {
    const axisGapBridges = gapBridges.filter(
      (node) => node.userData?.urdfAxis === axis,
    ) as THREE.Mesh[];

    assert.equal(axisGapBridges.length, 6, `${axis} should keep three bridge dashes on both sides`);

    const centers = axisGapBridges.map((mesh) => getGeometryAxisCenter(mesh, axis));
    assert.equal(
      centers.filter((value) => value > 0).length,
      3,
      `${axis} should keep three positive bridge dashes`,
    );
    assert.equal(
      centers.filter((value) => value < 0).length,
      3,
      `${axis} should keep three negative bridge dashes`,
    );
  }
});
