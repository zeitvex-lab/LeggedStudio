# 来源:
#   - EmpiricalNormalization: 00_resources/unilab_new/UniLab/src/unilab/algos/common/normalization.py
#   - GaussianDistribution: rsl_rl.modules.GaussianDistribution（UniLab hora/appo 依赖的外部包）
# 适配: EmpiricalNormalization 原文件即纯 torch，仅把 device 参数改为可选默认 cpu；
#       GaussianDistribution 是对 rsl_rl 同名类的**最小纯 torch 重实现**，只覆盖
#       UniLab hora/appo 代码实际用到的接口面（update/sample/log_prob/entropy/
#       kl_divergence/params/std_param/log_std_param/deterministic_output）。
# 删除: 未实现 rsl_rl 完整 GaussianDistribution 的 state-dependent std / tanh 变换等分支。

from __future__ import annotations

import copy
import math

import torch
import torch.nn as nn

from torch.distributions import Normal

Normal.set_default_validate_args(False)

_LOG_2_PI = math.log(2.0 * math.pi)


class EmpiricalNormalization(nn.Module):
    """Normalize mean and variance of observations using running statistics."""

    _mean: torch.Tensor
    _var: torch.Tensor
    _std: torch.Tensor
    count: torch.Tensor

    def __init__(self, shape, device=None, eps=1e-2):
        super().__init__()
        self.eps = eps
        device = device if device is not None else torch.device("cpu")
        self.device = device
        self.register_buffer("_mean", torch.zeros(shape).unsqueeze(0).to(device))
        self.register_buffer("_var", torch.ones(shape).unsqueeze(0).to(device))
        self.register_buffer("_std", torch.ones(shape).unsqueeze(0).to(device))
        self.register_buffer("count", torch.tensor(0, dtype=torch.long).to(device))

    @property
    def mean(self):
        return self._mean.squeeze(0).clone()

    @property
    def std(self):
        return self._std.squeeze(0).clone()

    @torch.no_grad()
    def forward(self, x: torch.Tensor, center: bool = True, update: bool = True) -> torch.Tensor:
        if self.training and update:
            self.update(x)
        if center:
            return torch.as_tensor((x - self._mean) / (self._std + self.eps))
        else:
            return torch.as_tensor(x / (self._std + self.eps))

    def update(self, x):
        batch_size = x.shape[0]
        batch_mean = torch.mean(x, dim=0, keepdim=True)
        batch_var = torch.var(x, dim=0, keepdim=True, unbiased=False)
        self.update_from_moments(batch_mean, batch_var, batch_size)

    @torch.no_grad()
    def update_from_moments(
        self,
        batch_mean: torch.Tensor,
        batch_var: torch.Tensor,
        batch_count: int | torch.Tensor,
    ) -> None:
        """Update running stats from precomputed batch moments."""
        batch_mean = batch_mean.to(device=self._mean.device, dtype=self._mean.dtype).view_as(
            self._mean
        )
        batch_var = batch_var.to(device=self._var.device, dtype=self._var.dtype).view_as(self._var)
        batch_count_t = torch.as_tensor(batch_count, device=self.count.device).to(
            dtype=self.count.dtype
        )

        new_count = self.count + batch_count_t

        # Welford's online algorithm
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
    """对 rsl_rl.modules.GaussianDistribution 的最小纯 torch 替代。

    支持 std_type="scalar"（全维度共享一个可学习 std）与
    std_type="log"（每维可学习 log std）。mean 由外部 update(mean) 注入。
    """

    def __init__(
        self,
        action_dim: int,
        init_std: float = 1.0,
        std_type: str = "scalar",
        clip_log_std: tuple[float, float] | None = (-20.0, 2.0),
        **kwargs,
    ) -> None:
        super().__init__()
        del kwargs  # 适配: 兼容 distribution_cfg 里混入的其他键（如 class_name）
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
        # 拷贝时直接置空 —— APPOLearner 对 actor 做 deepcopy 建 target 网络时需要。
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

    def deterministic_output(self, mean: torch.Tensor) -> torch.Tensor:
        return mean

    def log_prob(self, actions: torch.Tensor) -> torch.Tensor:
        return Normal(self.mean, self.std).log_prob(actions).sum(dim=-1)

    def kl_divergence(
        self,
        old_params: tuple[torch.Tensor, ...],
        new_params: tuple[torch.Tensor, ...],
    ) -> torch.Tensor:
        old_mean, old_std = old_params[0], old_params[1]
        new_mean, new_std = new_params[0], new_params[1]
        kl = torch.log(new_std / old_std + 1e-5) + (
            old_std.pow(2) + (old_mean - new_mean).pow(2)
        ) / (2.0 * new_std.pow(2)) - 0.5
        return kl.sum(dim=-1)
