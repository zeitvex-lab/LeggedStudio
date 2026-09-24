"""轮足形态 Kit（wheel-leg）—— 框架层唯一真值。

原先与四足 Kit 同住在 ``adapters/mjlab/velocity_task_kit``（B8 训练去包化）：
本目录的 ``mdp/`` 框架族与 ``velocity_env_cfg.py`` 只服务轮足三包
（``deeprobotics_m20`` / ``unitree_b2w`` / ``unitree_go2w``），
四足两包（``lite3`` / ``b2``）用的是另一组符号 —— 2026-09-19 按形态拆开
（决策依据见 ``00_know/90_归档/07_形态Kit设计草案.md``；两组符号完全不重叠，
因此是纯归属划分，无共享代码）。

包侧 stub 经 ``kit.mdp`` / ``kit.velocity_env_cfg`` / ``kit.ppo_runner_cfg_ex``
取用，所以本文件把三者都提到包命名空间。

越障技能族级化（2026-09-25）追加两项：``kit.terrains``（竞赛地形定义）与
``kit.traversal_env_cfg``（族级越障课程：竞赛地形集 + 障碍释放课程）。
包侧取用方式与前三者同（见 ``traversal_env_cfg.py`` 头注）。
"""

from . import mdp, terrains, traversal_env_cfg, velocity_env_cfg  # noqa: F401

__all__ = ["mdp", "terrains", "traversal_env_cfg", "velocity_env_cfg", "ppo_runner_cfg_ex"]


def ppo_runner_cfg_ex(
    experiment_name: str,
    *,
    run_name: str | None = None,
    max_iterations: int = 10001,
    save_interval: int = 1000,
    init_noise_std: float = 1.0,
    obs_normalization: bool = True,
    std_type: str = "scalar",
    learning_rate: float = 1.0e-3,
    entropy_coef: float = 0.01,
    max_grad_norm: float = 1.0,
    resume: bool = False,
    load_checkpoint: str | None = None,
):
    """轮足各包 rl_cfg 的 PPO runner 配置（B8 上移；m20/b2w/go2w 第二批、zex-w 第三批）。

    来源：三包 rl_cfg.py 的 ``make_X_runner_cfg`` 逐字共同正文（三份仅函数名与
    experiment_name 字符串不同——b2w/go2w 互为逐字副本、m20 是带 go2w 残留命名
    的同正文副本）。与 :func:`ppo_runner_cfg`（lite3/b2 语义）的差异都是**各自
    包里出现过的字面值**：默认 ``save_interval=1000`` / ``max_iterations=10001``、
    可调噪声/学习率/熵系数/梯度裁剪，以及 ``run_name`` / ``resume`` /
    ``load_checkpoint`` 三个 lite3/b2 版没有的维度。各包 stub 传自己的字面值
    即逐字段复现原 runner；包内包装函数签名不变。

    ``obs_normalization`` / ``std_type`` 是 zex-w 接入（2026-09-19，按"框架一致"
    裁决）时补的两个维度：zex-w 原 runner 是 ``obs_normalization=False`` +
    ``std_type="log"``，而 m20/b2w/go2w 是 True + "scalar"。**默认值即原三包语义**
    （不传就等于旧行为），zex-w 显式传自己的两个字面值。

    ``run_name`` 直接透传（含 None——三包原实现就是显式传 None，与
    RslRlOnPolicyRunnerCfg 的 dataclass 默认空串不同，语义等价实证以此为准；
    未显式传 run_name 的包传 ``""`` 即复现 dataclass 默认）；
    ``resume`` / ``load_checkpoint`` 按原实现的构造后赋值路径写回。
    """
    from mjlab.rl import (
        RslRlModelCfg,
        RslRlOnPolicyRunnerCfg,
        RslRlPpoAlgorithmCfg,
    )

    cfg = RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=obs_normalization,
            distribution_cfg={
                "class_name": "GaussianDistribution",
                "init_std": init_noise_std,
                "std_type": std_type,
            },
        ),
        critic=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=obs_normalization,
        ),
        algorithm=RslRlPpoAlgorithmCfg(
            value_loss_coef=1.0,
            use_clipped_value_loss=True,
            clip_param=0.2,
            entropy_coef=entropy_coef,
            num_learning_epochs=5,
            num_mini_batches=4,
            learning_rate=learning_rate,
            schedule="adaptive",
            gamma=0.99,
            lam=0.95,
            desired_kl=0.01,
            max_grad_norm=max_grad_norm,
        ),
        experiment_name=experiment_name,
        run_name=run_name,
        save_interval=save_interval,
        num_steps_per_env=24,
        max_iterations=max_iterations,
    )
    cfg.resume = resume
    if load_checkpoint is not None:
        cfg.load_checkpoint = load_checkpoint
    return cfg
