import type { RobotData, RobotState, UrdfLink, UrdfVisual } from '@/types';

type RobotSnapshot = RobotData | RobotState;
const MJCF_WORLD_LINK_ID = 'world';
const MJCF_WORLD_GEOM_LINK_PREFIX = 'world_geom_';

function hideVisual(visual: UrdfVisual): UrdfVisual {
  return visual.visible === false ? visual : { ...visual, visible: false };
}

function hideVisualBodies(visualBodies: UrdfVisual[] | undefined): UrdfVisual[] | undefined {
  if (!visualBodies || visualBodies.length === 0) {
    return visualBodies;
  }

  let changed = false;
  const nextBodies = visualBodies.map((body) => {
    if (body.visible === false) {
      return body;
    }

    changed = true;
    return hideVisual(body);
  });

  return changed ? nextBodies : visualBodies;
}

function hideMjcfWorldLink(link: UrdfLink): UrdfLink {
  const nextVisual = hideVisual(link.visual);
  const nextCollision = hideVisual(link.collision);
  const nextVisualBodies = hideVisualBodies(link.visualBodies);
  const nextCollisionBodies = hideVisualBodies(link.collisionBodies);

  if (
    link.visible === false &&
    nextVisual === link.visual &&
    nextCollision === link.collision &&
    nextVisualBodies === link.visualBodies &&
    nextCollisionBodies === link.collisionBodies
  ) {
    return link;
  }

  return {
    ...link,
    visible: false,
    visual: nextVisual,
    collision: nextCollision,
    visualBodies: nextVisualBodies,
    collisionBodies: nextCollisionBodies,
  };
}

function isMjcfWorldOwnedSyntheticLink(link: UrdfLink): boolean {
  return (
    link.id.startsWith(MJCF_WORLD_GEOM_LINK_PREFIX) ||
    link.name.startsWith(MJCF_WORLD_GEOM_LINK_PREFIX)
  );
}

function shouldHideMjcfWorldOwnedLink(link: UrdfLink): boolean {
  return (
    link.id === MJCF_WORLD_LINK_ID ||
    link.name === MJCF_WORLD_LINK_ID ||
    isMjcfWorldOwnedSyntheticLink(link)
  );
}

export function applyMjcfWorldVisibility<T extends RobotSnapshot>(
  robot: T,
  showMjcfWorldLink: boolean,
): T {
  if (showMjcfWorldLink || robot.inspectionContext?.sourceFormat !== 'mjcf') {
    return robot;
  }

  let changed = false;
  const nextLinks = Object.fromEntries(
    Object.entries(robot.links).map(([linkId, link]) => {
      if (!shouldHideMjcfWorldOwnedLink(link)) {
        return [linkId, link];
      }

      const nextLink = hideMjcfWorldLink(link);
      if (nextLink !== link) {
        changed = true;
      }

      return [linkId, nextLink];
    }),
  ) as T['links'];

  if (!changed) {
    return robot;
  }

  return {
    ...robot,
    links: nextLinks,
  };
}
