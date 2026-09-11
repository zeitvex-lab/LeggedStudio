import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { getRobotSceneNodeIndex } from './robotSceneNodeIndex';

test('getRobotSceneNodeIndex prefers existing robot link and joint maps', () => {
  const robot = new THREE.Group();

  const linkA = new THREE.Group();
  (linkA as any).isURDFLink = true;
  linkA.name = 'link_a';

  const linkB = new THREE.Group();
  (linkB as any).isURDFLink = true;
  linkB.name = 'link_b';

  const jointA = new THREE.Group();
  (jointA as any).isURDFJoint = true;
  jointA.name = 'joint_a';

  (robot as any).links = { link_a: linkA, link_b: linkB };
  (robot as any).joints = { joint_a: jointA };

  const originalTraverse = robot.traverse.bind(robot);
  let traverseCalls = 0;
  robot.traverse = ((callback: (object: THREE.Object3D) => void) => {
    traverseCalls += 1;
    return originalTraverse(callback);
  }) as typeof robot.traverse;

  const index = getRobotSceneNodeIndex(robot);

  assert.deepEqual(index.links, [linkA, linkB]);
  assert.deepEqual(index.joints, [jointA]);
  assert.equal(traverseCalls, 0);
});

test('getRobotSceneNodeIndex caches fallback traversal results', () => {
  const robot = new THREE.Group();

  const nested = new THREE.Group();
  const link = new THREE.Group();
  (link as any).isURDFLink = true;
  link.name = 'link_a';

  const joint = new THREE.Group();
  (joint as any).isURDFJoint = true;
  joint.name = 'joint_a';

  nested.add(link);
  nested.add(joint);
  robot.add(nested);

  const originalTraverse = robot.traverse.bind(robot);
  let traverseCalls = 0;
  robot.traverse = ((callback: (object: THREE.Object3D) => void) => {
    traverseCalls += 1;
    return originalTraverse(callback);
  }) as typeof robot.traverse;

  const firstIndex = getRobotSceneNodeIndex(robot);
  const secondIndex = getRobotSceneNodeIndex(robot);

  assert.deepEqual(firstIndex.links, [link]);
  assert.deepEqual(firstIndex.joints, [joint]);
  assert.equal(secondIndex, firstIndex);
  assert.equal(traverseCalls, 1);
});
