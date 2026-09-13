"""skrl environment wrapper for GenesisLab.

This is a thin shim around :mod:`skrl`'s own Isaac/Genesis wrappers so that
GenesisLab exposes an API identical to IsaacLab's ``isaaclab_rl.skrl``:

.. code-block:: python

    from genesis_rl.skrl import SkrlVecEnvWrapper
    from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv

    env = ManagerBasedRlEnv(...)
    env = SkrlVecEnvWrapper(env, ml_framework="torch")
"""

from __future__ import annotations

from typing import Literal

from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv


def SkrlVecEnvWrapper(  # noqa: N802 - follow upstream naming
    env: ManagerBasedRlEnv,
    ml_framework: Literal["torch", "jax", "jax-numpy"] = "torch",
    wrapper: Literal["auto", "isaaclab", "isaaclab-single-agent", "isaaclab-multi-agent"] = "isaaclab",
):
    """Wrap a :class:`ManagerBasedRlEnv` for use with :mod:`skrl`.

    The actual wrapping logic lives inside the :mod:`skrl` library. This
    function only performs a light type-check on the Genesis environment and
    then forwards to :func:`skrl.envs.wrappers.{torch,jax}.wrap_env`.
    """
    if not isinstance(env.unwrapped, ManagerBasedRlEnv) and not isinstance(env, ManagerBasedRlEnv):
        raise ValueError(
            "The environment must be an instance of ManagerBasedRlEnv. "
            f"Got type: {type(env)}"
        )

    if ml_framework.startswith("torch"):
        from skrl.envs.wrappers.torch import wrap_env
    elif ml_framework.startswith("jax"):
        from skrl.envs.wrappers.jax import wrap_env
    else:
        raise ValueError(
            f"Invalid ML framework for skrl: {ml_framework}. "
            "Available options are: 'torch', 'jax' or 'jax-numpy'"
        )

    return wrap_env(env, wrapper)

