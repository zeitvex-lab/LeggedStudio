import test from 'node:test';
import assert from 'node:assert/strict';

import { addChildToRobot, createEmptyRobot } from './builders.ts';
import { DEFAULT_LINK } from '@/types';

test('addChildToRobot anchors default child link geometry at the new joint origin', () => {
  const nextRobot = addChildToRobot(
    {
      name: 'robot',
      links: {
        base_link: {
          ...DEFAULT_LINK,
          id: 'base_link',
          name: 'base_link',
        },
      },
      joints: {},
      rootLinkId: 'base_link',
      selection: { type: 'link', id: 'base_link' },
    },
    'base_link',
  );

  assert.equal(nextRobot.selection.type, 'joint');
  assert.ok(nextRobot.selection.id);

  const newJoint = nextRobot.joints[nextRobot.selection.id];
  const newLink = nextRobot.links[newJoint.childLinkId];

  assert.equal(newJoint.origin.xyz.z, 0.25);
  assert.equal(newLink.visual.origin.xyz.z, 0.25);
  assert.equal(newLink.collision.origin.xyz.z, 0.25);
  assert.ok(newLink.inertial?.origin);
  assert.equal(newLink.inertial.origin.xyz.z, 0.25);
});

test('createEmptyRobot places the default base link frame at the bottom of the body', () => {
  const robot = createEmptyRobot();
  const rootLink = robot.links[robot.rootLinkId];

  assert.equal(rootLink.visual.origin.xyz.z, 0.25);
  assert.equal(rootLink.collision.origin.xyz.z, 0.25);
  assert.ok(rootLink.inertial?.origin);
  assert.equal(rootLink.inertial.origin.xyz.z, 0.25);
});
