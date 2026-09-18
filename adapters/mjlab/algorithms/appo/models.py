# 来源: rsl_rl.models.MLPModel（UniLab appo/learner.py 依赖的外部包）+
#       00_resources/unilab_new/UniLab/src/unilab/algos/common/normalization.py
# 适配: 用纯 torch 重写 APPO learner 需要的最小 actor/critic 模型面
#       （learner 代码访问 actor.mlp / actor.obs_normalizer / actor.distribution /
#       get_output_log_prob / output_mean / output_std）。
#       EmpiricalNormalization 与 GaussianDistribution 为最小重实现
#       （与 hora/modules.py 同源，各自成目录以便独立 import）。
# 删除: rsl_rl MLPModel 的 recurrent 变体、TensorDict 分组观测（obs_groups）。
#
# 非对称结构: APPOActor 只吃本体观测 policy_obs_dim；APPOCritic 只吃特权观测
# privileged_obs_dim（含高度图/真实状态等），两维度可以不同 —— 这是 APPO 与
# 标准 PPO（actor/critic 同观测）的关键差异。

from __future__ import annotations

import copy
import math

import torch
import torch.nn as nn
from torch.distributions import Normal

Normal.set_default_validate_args(False)

_LOG_2_PI = math.log(2.0 * math.pi)


class EmpiricalNormalization(nn.Module):
    """运行均值/方差观测归一化（Welford 在线更新）。纯 torch 版。"""

    def __init__(self, shape, device=None, eps=1e-2):
        super().__init__()
        self.eps = eps
        device = device if device is not None else torch.device("cpu")
        self.register_buffer("_mean", torch.zeros(shape).unsqueeze(0).to(device))
        self.register_buffer("_var", torch.ones(shape).unsqueeze(0).to(device))
        self.register_buffer("_std", torch.ones(shape).unsqueeze(0).to(device))
        self.register_buffer("count", torch.tensor(0, dtype=torch.long).to(device))

    @torch.no_grad()
    def forward(self, x: torch.Tensor, center: bool = True, update: bool = True) -> torch.Tensor:
        if self.training and update:
            self.update(x)
        if center:
            return (x - self._mean) / (self._std + self.eps)
        return x / (self._std + self.eps)

    def update(self, x):
        batch_size = x.shape[0]
        batch_mean = torch.mean(x, dim=0, keepdim=True)
        batch_var = torch.var(x, dim=0, keepdim=True, unbiased=False)
        batch_mean = batch_mean.to(self._mean.device, self._mean.dtype)
        batch_var = batch_var.to(self._var.device, self._var.dtype)
        batch_count_t = torch.as_tensor(batch_size, device=self.count.device).to(
            dtype=self.count.dtype
        )
        new_count = self.count + batch_count_t
        delta = batch_mean - self._mean
        self._mean.copy_(self._mean + delta * (batch_count_t / new_count))
        delta2 = batch_mean - self._mean
        m_a = self._var * self.count
        m_b = batch_var * batch_count_t
        M2 = m_a + m_b + delta2.pow(2) * (self.count * batch_count_t / new_count)
        self._var.copy_(M2 / new_count)
        self._std.copy_(self._var.sqrt())
        self.count.copy_(new_count)

    def inverse(self, y):
        return y * (self._std + self.eps) + self._mean


class GaussianDistribution(nn.Module):
    """rsl_rl GaussianDistribution 的最小替代（scalar / log 两种 std_type）。"""

    def __init__(
        self,
        action_dim: int,
        init_std: float = 1.0,
        std_type: str = "scalar",
        clip_log_std: tuple[float, float] | None = (-20.0, 2.0),
    ) -> None:
        super().__init__()
        if std_type not in ("scalar", "log"):
            raise ValueError(f"Unsupported std_type: {std_type}")
        self.action_dim = int(action_dim)
        self.std_type = std_type
        if std_type == "scalar":
            self.std_param = nn.Parameter(torch.ones(1) * float(init_std))
            self.log_std_param = None
        else:
            self.std_param = None
            self.log_std_param = nn.Parameter(
                torch.full((self.action_dim,), float(math.log(init_std)))
            )
        self.clip_log_std = clip_log_std
        self._mean: torch.Tensor | None = None

    def __deepcopy__(self, memo):
        # 适配: _mean 是临时前向状态（可能是非叶张量，deepcopy 会报错），
        # APPOLearner 在 __init__ 里 deepcopy actor 建 target 网络时需要安全拷贝。
        cls = self.__class__
        new = cls.__new__(cls)
        memo[id(self)] = new
        for key, value in self.__dict__.items():
            if key == "_mean":
                continue
            new.__dict__[key] = copy.deepcopy(value, memo)
        new._mean = None
        return new

    def update(self, mean: torch.Tensor) -> "GaussianDistribution":
        self._mean = mean
        return self

    @property
    def mean(self) -> torch.Tensor:
        assert self._mean is not None, "call update(mean) first"
        return self._mean

    @property
    def std(self) -> torch.Tensor:
        if self.std_type == "scalar":
            return self.std_param.clamp_min(1e-6).expand_as(self.mean)
        log_std = self.log_std_param
        if self.clip_log_std is not None:
            log_std = log_std.clamp(*self.clip_log_std)
        return log_std.exp().expand_as(self.mean)

    @property
    def entropy(self) -> torch.Tensor:
        return (torch.log(self.std) + 0.5 * (1.0 + _LOG_2_PI)).sum(dim=-1)

    @property
    def params(self) -> tuple[torch.Tensor, torch.Tensor]:
        return (self.mean, self.std)

    def sample(self) -> torch.Tensor:
        return Normal(self.mean, self.std).sample()

    def log_prob(self, actions: torch.Tensor) -> torch.Tensor:
        return Normal(self.mean, self.std).log_prob(actions).sum(dim=-1)


def _build_mlp(input_dim: int, hidden_dims, activation: str = "elu") -> nn.Sequential:
    act = {"elu": nn.ELU, "relu": nn.ReLU, "tanh": nn.Tanh}[activation]
    layers: list[nn.Module] = []
    last = int(input_dim)
    for h in hidden_dims:
        layers += [nn.Linear(last, int(h)), act()]
        last = int(h)
    layers.append(nn.Linear(last, 1))
    return nn.Sequential(*layers)


class APPOActor(nn.Module):
    """APPO actor 本体: 只吃本体观测（policy obs），输出高斯动作分布。"""

    is_recurrent: bool = False

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims=(256, 128, 64),
        activation: str = "elu",
        init_noise_std: float = 1.0,
        std_type: str = "scalar",
        obs_normalization: bool = False,
    ) -> None:
        super().__init__()
        self.obs_dim = int(obs_dim)
        self.action_dim = int(action_dim)
        self.obs_normalizer = EmpiricalNormalization(self.obs_dim) if obs_normalization else nn.Identity()
        act = {"elu": nn.ELU, "relu": nn.ReLU, "tanh": nn.Tanh}[activation]
        layers: list[nn.Module] = []
        last = self.obs_dim
        for h in hidden_dims:
            layers += [nn.Linear(last, int(h)), act()]
            last = int(h)
        layers.append(nn.Linear(last, self.action_dim))
        self.mlp = nn.Sequential(*layers)
        self.distribution = GaussianDistribution(
            self.action_dim, init_std=init_noise_std, std_type=std_type
        )

    def forward(
        self, obs: torch.Tensor, stochastic_output: bool = False
    ) -> torch.Tensor:
        mean = self.mlp(self.obs_normalizer(obs))
        self.distribution.update(mean)
        if stochastic_output:
            return self.distribution.sample()
        return mean

    @property
    def output_mean(self) -> torch.Tensor:
        return self.distribution.mean

    @property
    def output_std(self) -> torch.Tensor:
        return self.distribution.std

    @property
    def output_entropy(self) -> torch.Tensor:
        return self.distribution.entropy

    def get_output_log_prob(self, actions: torch.Tensor) -> torch.Tensor:
        return self.distribution.log_prob(actions)

    def update_normalization(self, obs: torch.Tensor) -> None:
        if isinstance(self.obs_normalizer, EmpiricalNormalization):
            self.obs_normalizer.update(obs)


class APPOCritic(nn.Module):
    """APPO critic: 只吃特权观测（privileged obs），单输出 value。"""

    is_recurrent: bool = False

    def __init__(
        self,
        obs_dim: int,
        hidden_dims=(256, 128, 64),
        activation: str = "elu",
        obs_normalization: bool = False,
    ) -> None:
        super().__init__()
        self.obs_dim = int(obs_dim)
        self.obs_normalizer = EmpiricalNormalization(self.obs_dim) if obs_normalization else nn.Identity()
        self.mlp = _build_mlp(self.obs_dim, hidden_dims, activation)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.mlp(self.obs_normalizer(obs)).squeeze(-1)

    def update_normalization(self, obs: torch.Tensor) -> None:
        if isinstance(self.obs_normalizer, EmpiricalNormalization):
            self.obs_normalizer.update(obs)
