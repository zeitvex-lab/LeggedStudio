"""Base environment for manager-based Genesis RL environments."""

from __future__ import annotations

from dataclasses import MISSING
import logging
import random
from typing import ClassVar, TYPE_CHECKING, Dict

import torch

from genesislab.engine.scene import SceneCfg
from genesislab.utils.configclass import configclass
from genesislab.utils.timing import timed_block

from genesislab.engine.scene import LabScene
from genesislab.engine.entity import LabEntity
from genesislab.envs.common import VecEnvObs, VecEnvStepReturn
from genesislab.managers.action_manager import ActionManager
from genesislab.managers.command_manager import CommandManager, NullCommandManager
from genesislab.managers.observation_manager import ObservationManager
from genesislab.managers.reward_manager import RewardManager
from genesislab.managers.termination_manager import TerminationManager
from genesislab.managers import EventManager

if TYPE_CHECKING:
    from genesislab.engine.gstype import gs


logger = logging.getLogger(__name__)

class ManagerBasedGenesisEnv:
    """Manager-based RL environment for Genesis.

    This environment orchestrates managers (action, observation, reward, termination,
    command) and provides a clean interface for RL training. It maintains batched
    state buffers and handles decimation between physics and control steps.

    The step pipeline is:
    1. Process actions via ActionManager
    2. Apply actions and step physics (with decimation)
    3. Compute observations via ObservationManager
    4. Compute rewards via RewardManager
    5. Compute terminations via TerminationManager
    6. Reset terminated environments
    """

    # Vectorized env metadata, aligned with IsaacLab/mjlab.
    is_vector_env: ClassVar[bool] = True
    """Whether this environment manages a batch of parallel sub-environments."""

    metadata: ClassVar[dict[str, list]] = {
        "render_modes": [None, "rgb_array"],
    }
    """Environment metadata (render modes, fps, etc.)."""
    cfg: "ManagerBasedGenesisEnvCfg"

    def __init__(self, cfg: "ManagerBasedGenesisEnvCfg", device: str = "cuda"):
        """Initialize the environment.

        Args:
            cfg: Environment configuration.
            device: Device to use for tensors ('cuda' or 'cpu').
        """
        self.cfg = cfg
        self.device = device

        # Set random seed if provided
        if cfg.seed is not None:
            self.seed(cfg.seed)

        # Build scene
        self._scene = LabScene(cfg.scene, device=device)
        self._scene.build(env=self)

        # Compute step timing
        self.physics_dt: float = cfg.scene.sim_options.dt
        """Physics simulation step size."""

        self.step_dt: float = self.physics_dt * cfg.decimation
        """Environment step size (physics_dt * decimation)."""

        # Episode management
        self._max_episode_length_s: float = cfg.episode_length_s
        self.is_finite_horizon: bool = cfg.is_finite_horizon
        if self._max_episode_length_s is not None:
            self._max_episode_length: int = int(self._max_episode_length_s / self.step_dt)
        else:
            self._max_episode_length = None

        # Initialize buffers
        self.num_envs: int = self._scene.num_envs
        self.episode_length_buf = torch.zeros(self.num_envs, dtype=torch.long, device=device)
        self.common_step_counter = 0

        # Load managers
        self._load_managers()

        # Configure Gym-style spaces
        self._configure_spaces()

        # Apply startup events if event manager is configured
        if self.event_manager is not None and "startup" in self.event_manager.available_modes:
            self.event_manager.apply(mode="startup")

    def seed(self, seed: int = None) -> None:
        """Set random seed for reproducibility.

        Args:
            seed: Random seed. If None, uses a random seed.
        """
        if seed is None:
            seed = random.randint(0, 2**31 - 1)
        self.cfg.seed = seed
        torch.manual_seed(seed)
        random.seed(seed)
        # Note: Genesis may have its own RNG that should be seeded separately

    def _load_managers(self) -> None:
        """Load and initialize all managers."""
        # Managers can accept either configclass instances or dictionaries
        # Pass configclass instances directly to preserve type information
        
        # Command manager (optional) - must be initialized first as observations may depend on it
        if self.cfg.commands is not None:
            self.command_manager = CommandManager(cfg=self.cfg.commands, env=self)
        else:
            self.command_manager = NullCommandManager()

        # Action manager
        self.action_manager = ActionManager(cfg=self.cfg.actions, env=self)

        # Observation manager
        self.observation_manager = ObservationManager(cfg=self.cfg.observations, env=self)

        # Reward manager
        self.reward_manager = RewardManager(
            cfg=self.cfg.rewards,
            env=self,
        )

        # Termination manager
        self.termination_manager = TerminationManager(cfg=self.cfg.terminations, env=self)

        # Event manager (optional)
        self.event_manager = EventManager(cfg=self.cfg.events, env=self) if self.cfg.events is not None else None

        # Report initialized managers (IsaacLab-style summary).
        print("[ManagerBasedGenesisEnv] Command manager: %s", self.command_manager)
        print("[ManagerBasedGenesisEnv] Action manager: %s", self.action_manager)
        print("[ManagerBasedGenesisEnv] Observation manager: %s", self.observation_manager)
        print("[ManagerBasedGenesisEnv] Reward manager: %s", self.reward_manager)
        print("[ManagerBasedGenesisEnv] Termination manager: %s", self.termination_manager)
        print("[ManagerBasedGenesisEnv] Event manager: %s", self.event_manager)

    def _configure_spaces(self) -> None:
        """Configure Gym-style observation and action spaces."""
        # Action space
        action_dim = self.action_manager.total_action_dim
        self.action_space = torch.zeros((self.num_envs, action_dim), device=self.device)

        # Observation space
        # This would be configured based on observation_manager output shapes
        # For now, we'll compute it dynamically
        self.observation_space = None  # Will be set after first observation

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def max_episode_length_s(self) -> float:
        """Maximum episode length in seconds, if configured."""
        return self._max_episode_length_s

    @property
    def max_episode_length(self) -> int:
        """Maximum episode length in environment steps, if configured."""
        return self._max_episode_length

    # -------------------------------------------------------------------------
    # Core API
    # -------------------------------------------------------------------------

    @property
    def scene(self) -> LabScene:
        """The LabScene instance (provides access to scene, entities, sensors, query and control)."""
        return self._scene

    @property
    def gsscene(self) -> "gs.Scene":
        """The Genesis Scene instance."""
        return self._scene.gs_scene

    @property
    def entities(self) -> dict[str, LabEntity]:
        """Dictionary of entity wrappers keyed by name.

        Each entity provides a `data` property for accessing state:
        - `env.entities["go2"].data.joint_pos` - joint positions
        - `env.entities["go2"].data.root_pos_w` - root position in world frame
        - etc.
        """
        return self._scene.entities

    def reset(
        self,
        seed: int = None,
        env_ids: torch.Tensor = None,
        options: dict[str, object] = None,
    ) -> tuple[VecEnvObs, dict[str, object]]:
        """Reset the environment.

        Args:
            seed: Optional random seed for this reset.
            env_ids: Environment indices to reset. If None, resets all environments.
            options: Additional reset options.

        Returns:
            Tuple of (observations, info) where observations is a dict of tensors
            and info contains additional information.
        """
        # Re-seed if provided
        if seed is not None:
            self.seed(seed)

        # Determine which environments to reset
        if env_ids is None:
            env_ids = torch.arange(self.num_envs, device=self.device)
        elif isinstance(env_ids, (list, tuple)):
            env_ids = torch.tensor(env_ids, dtype=torch.long, device=self.device)

        # Reset scene
        self._scene.controller.reset(env_ids=env_ids)

        # Reset episode counters
        self.episode_length_buf[env_ids] = 0

        # Apply reset events if event manager is configured
        if self.event_manager is not None and "reset" in self.event_manager.available_modes:
            self.event_manager.apply(mode="reset", env_ids=env_ids, global_env_step_count=self.common_step_counter)

        # Reset managers and collect extras
        manager_extras = {}
        manager_extras.update(self.action_manager.reset(env_ids=env_ids))
        manager_extras.update(self.observation_manager.reset(env_ids=env_ids))
        manager_extras.update(self.reward_manager.reset(env_ids=env_ids))
        manager_extras.update(self.termination_manager.reset(env_ids=env_ids))
        manager_extras.update(self.command_manager.reset(env_ids=env_ids))
        
        # Reset event manager and collect extras
        if self.event_manager is not None:
            event_extras = self.event_manager.reset(env_ids=env_ids)
            manager_extras.update(event_extras)

        # Compute initial observations
        obs_buf = self.observation_manager.compute(update_history=True)

        # For alignment with IsaacLab/mjlab, expose manager extras at top level.
        info = dict(manager_extras)
        return obs_buf, info

    def step(self, action: torch.Tensor) -> VecEnvStepReturn:
        """Step the environment (simulation-only for the base Genesis env).
        
        This method:
        1. Processes actions via the ActionManager.
        2. Advances physics (with decimation) and updates sensors.
        3. Increments episode counters.
        4. Computes observations via the ObservationManager.
        
        It does NOT compute rewards or terminations. Higher-level RL wrappers
        such as :class:`ManagerBasedRlEnv` extend this behavior to include
        reward and termination logic.
        """
        # Process actions and advance simulation
        self._step_simulation(action)

        # Compute observations only
        with timed_block("observations.compute"):
            obs_buf = self.observation_manager.compute(update_history=True)

        # For non-RL usage, return zero rewards and no terminations by default.
        reward_buf = torch.zeros(self.num_envs, device=self.device)
        reset_terminated = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        reset_time_outs = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        info: dict[str, dict] = {
            "time_outs": reset_time_outs,
            "terminated": reset_terminated,
            "log": {},
        }

        return obs_buf, reward_buf, reset_terminated, reset_time_outs, info

    def _step_simulation(self, action: torch.Tensor) -> None:
        """Advance the simulation by one environment step.

        This helper encapsulates the core simulation pipeline shared across
        RL and non-RL environments:

        1. Process actions via ActionManager.
        2. Apply actions and step physics (with decimation).
        3. Update sensors.
        4. Increment episode counters.
        """
        # Process actions
        self.action_manager.process_action(action.to(self.device))

        # Physics stepping loop (decimation)
        with timed_block("physics (apply_action+step)"):
            for _ in range(self.cfg.decimation):
                # Apply actions
                self.action_manager.apply_action()
                # Step physics
                self._scene.controller.step()

        # Update sensors (if any) at physics rate.
        self._update_sensors()

        # Update episode counters
        self.episode_length_buf += 1
        self.common_step_counter += 1

    def _update_sensors(self) -> None:
        """Update any scene-attached sensors after a physics step."""
        sensors = self._scene.sensors
        for sensor_name, sensor in sensors.items():
            if not hasattr(sensor, "update"):
                raise AttributeError(
                    f"Sensor '{sensor_name}' does not have 'update' method. "
                    f"All sensors must implement the update() method."
                )
            sensor.update(dt=self.physics_dt)

    def _reset_idx(self, env_ids: torch.Tensor) -> None:
        """Reset specific environments.

        Args:
            env_ids: Environment indices to reset.
        """
        # Reset scene
        self._scene.controller.reset(env_ids=env_ids)

        # Reset episode counters
        self.episode_length_buf[env_ids] = 0

        # Reset managers and collect extras (episode-level summaries, metrics, etc.).
        manager_extras: dict[str, object] = {}
        manager_extras.update(self.action_manager.reset(env_ids=env_ids))
        manager_extras.update(self.observation_manager.reset(env_ids=env_ids))
        manager_extras.update(self.reward_manager.reset(env_ids=env_ids))
        manager_extras.update(self.termination_manager.reset(env_ids=env_ids))
        manager_extras.update(self.command_manager.reset(env_ids=env_ids))

        return manager_extras


@configclass
class ManagerBasedGenesisEnvCfg:
    """Configuration for a manager-based Genesis environment.
    
    This base config is agnostic to any particular MDP or RL algorithm. It captures
    the high-level environment settings:
    
    - Scene configuration (robots, terrain, sensors, simulation dt, etc.).
    - Manager configurations (observation, action, reward, termination, commands).
    - Generic episode timing and reward scaling options that higher-level RL
      wrappers may interpret according to their own semantics.
    """

    # Base environment configuration
    decimation: int = 1
    """Number of physics steps per environment step. Environment dt = scene.dt * decimation."""

    scene: SceneCfg = SceneCfg()
    """Scene configuration describing robots, terrain, sensors and simulation options."""

    # Manager configs are kept intentionally untyped here; task configs are expected
    # to populate them with the appropriate term config objects from the managers.
    observations: object = MISSING
    """Observation groups configuration (typically `ObservationGroupCfg` instances)."""

    actions: object = MISSING
    """Action term configurations."""

    rewards: object = MISSING
    """Reward term configurations."""

    terminations: object = MISSING
    """Termination term configurations."""

    commands: object = MISSING
    """Command term configurations. If None, no command manager is created."""

    events: object = MISSING
    """Event term configurations. If None, no event manager is created.
    
    Events are triggered at different simulation stages:
    - "startup": Once at initialization
    - "reset": On episode reset
    - "interval": Periodically during simulation
    
    Please refer to the :class:`genesislab.managers.EventManager` class for more details.
    """

    # RL-specific configuration
    seed: int = 42
    """Random seed for reproducibility."""

    episode_length_s: float = 20
    """Episode length in seconds. If None, horizon is infinite unless terminated by terms."""

    is_finite_horizon: bool = False
    """Whether episodes are treated as finite-horizon (timeouts counted as truncations)."""

