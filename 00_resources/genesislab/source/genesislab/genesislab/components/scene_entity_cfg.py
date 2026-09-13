"""Genesis-specific scene entity configuration utilities.

This module provides a minimal ``SceneEntityCfg`` that follows the IsaacLab /
mjlab pattern but resolves against Genesis entities instead of MuJoCo entities.

The intent is that term configs may carry lightweight references to entities
by name, and the manager base will call :meth:`resolve` once at construction
time so that term functions can access the resolved handle efficiently.
"""

from __future__ import annotations

from dataclasses import MISSING
from typing import List, TYPE_CHECKING

from genesislab.engine.entity import LabEntity
from genesislab.utils.configclass import configclass
from genesislab.utils.configclass.string import resolve_matching_names

if TYPE_CHECKING:
    from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv
    from genesislab.engine.gstype import KinematicEntity

@configclass
class SceneEntityCfg:
    """Configuration for referencing a scene entity in manager term configs.

    This is a Genesis-centric counterpart of IsaacLab's ``SceneEntityCfg``.
    It supports entity name resolution and body/joint name-to-index conversion.
    """

    entity_name: str = MISSING
    """Logical name of the entity as used in the scene.
    
    This field is also accessible as ``name`` for compatibility with IsaacLab.
    """

    name: str = None
    """Alias for entity_name (IsaacLab compatibility). If set, takes precedence over entity_name."""

    body_names: str | list[str] = None
    """The names of the bodies from the entity required by the term. Defaults to None.

    The names can be either body names or a regular expression matching the body names.
    These are converted to body indices on initialization via :meth:`resolve` and passed
    to the term function as a list of body indices under :attr:`body_ids`.
    """

    body_ids = None
    """The indices of the bodies from the entity required by the term. Defaults to slice(None), which means
    all the bodies in the entity.

    If :attr:`body_names` is specified, this is filled in automatically on resolution.
    """

    joint_names: str | list[str] = None
    """The names of the joints from the entity required by the term. Defaults to None.

    The names can be either joint names or a regular expression matching the joint names.
    These are converted to joint indices on initialization via :meth:`resolve` and passed
    to the term function as a list of joint indices under :attr:`joint_ids`.
    """

    joint_ids = None
    """The indices of the joints from the entity required by the term. Defaults to slice(None), which means
    all the joints in the entity (if present).

    If :attr:`joint_names` is specified, this is filled in automatically on resolution.
    """

    preserve_order: bool = False
    """Whether to preserve indices ordering to match with that in the specified joint or body names.
    Defaults to False.

    If False, the ordering of the indices are sorted in ascending order. Otherwise, the indices
    are preserved in the order of the specified joint or body names.
    """

    resolved: object = None
    """Resolved engine-level entity handle. Set by :meth:`resolve`."""

    def __post_init__(self):
        """Post-initialization to handle name alias."""
        # If name is set, use it as entity_name (IsaacLab compatibility)
        if self.name is not None:
            self.entity_name = self.name
        # If entity_name is set but name is not, set name for compatibility
        elif self.entity_name != MISSING:
            self.name = self.entity_name

    def resolve(self, container: dict, env: "ManagerBasedRlEnv" = None) -> None:
        """Resolve the entity reference against a container and convert body/joint names to indices.

        Args:
            container: Either a mapping (name → entity) or an object with
                attributes or items corresponding to entities. For body/joint resolution,
                the container should provide access to the scene or environment.
            env: Optional environment instance. If provided and the entity is a sensor,
                this will be used to resolve the sensor's associated entity for body/joint resolution.
        """
        # Ensure name is set
        if self.name is None and self.entity_name != MISSING:
            self.name = self.entity_name
        elif self.name is None:
            raise ValueError("SceneEntityCfg must have either 'name' or 'entity_name' set.")

        # Resolve entity reference
        entity = None
        resolved_obj = None  # Could be entity or sensor
        
        if isinstance(container, dict):
            if self.name not in container:
                # Check if it's a sensor (requires env)
                if env is not None and hasattr(env, "scene") and hasattr(env.scene, "sensors"):
                    if self.name in env.scene.sensors:
                        resolved_obj = env.scene.sensors[self.name]
                        # For sensors, get the associated entity (if needed for body/joint resolution)
                        if hasattr(resolved_obj, "cfg") and hasattr(resolved_obj.cfg, "entity_name"):
                            entity_name = resolved_obj.cfg.entity_name
                            if entity_name in container:
                                entity = container[entity_name]
                            elif hasattr(env, "entities") and entity_name in env.entities:
                                # Try to get from env.entities (Entity wrapper)
                                entity_wrapper = env.entities[entity_name]
                                if hasattr(entity_wrapper, "raw_entity"):
                                    entity = entity_wrapper.raw_entity
                                elif hasattr(entity_wrapper, "_raw_entity"):
                                    entity = entity_wrapper._raw_entity
                                else:
                                    entity = entity_wrapper
                if entity is None and resolved_obj is None:
                    raise KeyError(
                        f"SceneEntityCfg could not resolve entity or sensor '{self.name}' "
                        f"in container keys: {list(container.keys())}."
                    )
            else:
                resolved_obj = container[self.name]
                entity = resolved_obj
        elif hasattr(container, self.name):
            resolved_obj = getattr(container, self.name)
            entity = resolved_obj
        else:
            raise AttributeError(
                f"SceneEntityCfg could not resolve entity '{self.name}' "
                f"from container of type {type(container)}."
            )

        self.resolved = resolved_obj

        # Resolve body names to indices if needed
        # For sensors, we need the associated LabEntity, not the sensor itself
        lab_entity = None
        if self.body_names is not None or self.joint_names is not None:
            if entity is None and env is not None:
                # Try to get LabEntity from sensor's associated entity
                if hasattr(resolved_obj, "cfg") and hasattr(resolved_obj.cfg, "entity_name"):
                    entity_name = resolved_obj.cfg.entity_name
                    # Prefer env.entities (LabEntity objects)
                    if hasattr(env, "entities") and entity_name in env.entities:
                        lab_entity = env.entities[entity_name]
                    elif hasattr(env, "scene") and hasattr(env.scene, "entities"):
                        if entity_name in env.scene.entities:
                            lab_entity = env.scene.entities[entity_name]
            elif entity is not None:
                # If entity is already a LabEntity, use it directly
                if isinstance(entity, LabEntity):
                    lab_entity = entity
                # Otherwise, try to find the LabEntity wrapper
                elif env is not None:
                    # Try to find by name in container
                    if isinstance(container, dict) and self.name in container:
                        potential_entity = container[self.name]
                        if isinstance(potential_entity, LabEntity):
                            lab_entity = potential_entity
                    # Try to find in env.entities
                    if lab_entity is None and hasattr(env, "entities"):
                        for name, ent in env.entities.items():
                            if hasattr(ent, "raw_entity") and ent.raw_entity is entity:
                                lab_entity = ent
                                break
        
        # Resolve body names to indices if needed
        if self.body_names is not None:
            if lab_entity is not None:
                self._resolve_body_names(lab_entity)
            else:
                raise ValueError(
                    f"Cannot resolve body_names for '{self.name}': "
                    "LabEntity not found. For sensors, ensure the environment is provided to resolve()."
                )

        # Resolve joint names to indices if needed
        if self.joint_names is not None:
            if lab_entity is not None:
                self._resolve_joint_names(lab_entity)
            else:
                raise ValueError(
                    f"Cannot resolve joint_names for '{self.name}': "
                    "LabEntity not found. For sensors, ensure the environment is provided to resolve()."
                )

    def _resolve_body_names(self, entity: "LabEntity") -> None:
        """Convert body names to body indices based on regex matching.

        Args:
            entity: The Genesis entity object with link/body information.
        """

        # Resolve matching names
        if isinstance(self.body_names, str): body_names_list = [self.body_names]
        else: body_names_list = self.body_names

        try:
            body_indices, matched_names = resolve_matching_names(
                body_names_list, entity.link_names, preserve_order=self.preserve_order
            )
            self.body_ids = body_indices
            if len(body_indices) == entity.n_links: self.body_ids = slice(None)
        except ValueError as e:
            raise ValueError(
                f"Could not resolve body names '{self.body_names}' for entity '{self.name}'. "
                f"Available body/link names: {entity.link_names}. Error: {e}"
            )

    def _resolve_joint_names(self, entity: "LabEntity") -> None:
        """Convert joint names to joint indices based on regex matching.

        Args:
            entity: The Genesis entity object with joint information.
        """

        # Get all joint names - we need to iterate to find all joints
        # This is a simplified approach; actual implementation may vary
        joint_names = entity.data.joint_names
        joint_index = 0

        if not joint_names:
            raise ValueError(
                f"Could not find any joints in entity '{self.name}'. "
                "Cannot resolve joint names."
            )

        # Resolve matching names
        if isinstance(self.joint_names, str):
            joint_names_list = [self.joint_names]
        else:
            joint_names_list = self.joint_names

        try:
            joint_indices, matched_names = resolve_matching_names(
                joint_names_list, joint_names, preserve_order=self.preserve_order
            )
            self.joint_ids = joint_indices
            # Performance optimization: if all joints are selected, use slice(None)
            if hasattr(entity, "num_joints") and len(joint_indices) == entity.num_joints:
                self.joint_ids = slice(None)
        except ValueError as e:
            raise ValueError(
                f"Could not resolve joint names '{self.joint_names}' for entity '{self.name}'. "
                f"Available joint names: {joint_names}. Error: {e}"
            )

