"""族级镜像对称机制（源 fork 的对称 PPO 与左右镜像置换）。

来源：`go2_skills/rear_stand/mdp/symmetry.py` 的 `SourceMirrorSymmetry` /
`SourceSymmetricPPO`（**与机型无关**，逐字上移）；机型侧的**有符号置换表**
（`_REAR_STAND_*` / `_SPRING_*`）不再随类走：四足族的镜像就是"腿对互换 + 髋外展取反"，
由 :func:`leg_pair_mirror` 按"腿数 × 每腿角色数"派生（见其 docstring 的推导）。

先例：这两个类原本只住在 go2 包里，于是 spring_jump 与 rear_stand 只能共用同一份
包内实现；上移后族内任何机型都能用同一套对称机制。
"""

from __future__ import annotations

from typing import Any, cast

import torch
import torch.nn.functional as F
from rsl_rl.algorithms import PPO
from rsl_rl.extensions import Symmetry
from rsl_rl.models import MLPModel
from rsl_rl.storage import RolloutStorage
from tensordict import TensorDict


def leg_pair_mirror(legs: int, roles: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """左右镜像的有符号置换（腿段级）：返回 `(index, sign)`，长度 = `legs × roles`。

    族约定（与动作接口序一致）：动作/关节段按"腿优先、每腿 roles 个角色"排列，
    腿序里相邻两条为一对左右腿（`leg_ids` 前腿在前，四足 = (FL,FR) 与 (RL,RR)）。
    镜像 = **每对左右腿互换**、且**第一个角色（髋外展）取反**、其余角色保持。

    为什么不是机型数据：这个置换只由"腿数 × 角色数"决定，与关节怎么命名无关 ——
    go2 的源置换 `(3,4,5, 0,1,2, 9,10,11, 6,7,8)` 与符号 `(-1,1,1)×4` 正是它在
    4 腿 3 角色下的取值（逐值核对见 `backend/test_family_sk*` 或对拍记录）。
    """
    if legs % 2:
        raise ValueError(f"镜像要求腿数为偶数（左右成对），收到 {legs}")
    pairs = [(index, index + 1) for index in range(0, legs, 2)]
    order = [leg for pair in pairs for leg in (pair[1], pair[0])]
    index = tuple(leg * roles + role for leg in order for role in range(roles))
    sign = tuple(-1 if role == 0 else 1 for _ in order for role in range(roles))
    return index, sign


def frame_mirror(
    action_index: tuple[int, ...],
    action_sign: tuple[int, ...],
    *,
    leading_index: tuple[int, ...],
    leading_sign: tuple[int, ...],
    blocks: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """把"腿段置换"扩到整帧：前导段用给定的（列, 符号），其后 `blocks` 个关节类段各自置换。

    观测帧由若干定长段拼成（命令 / 角速度 / 欧拉角 / 位置 / 速度 / 动作…）。**前导段**
    （命令与姿态量）的镜像符号是**逐字段**的物理量镜像（`v_y → -v_y`、`ω_x,ω_z → -ω_x,-ω_z`
    …），由技能帧布局给定；**关节类段**都按同一套腿段布局排列，于是整帧 = 前导 + 逐段置换。
    """
    if len(action_index) != len(action_sign):
        raise ValueError("index/sign 长度不一致")
    if len(leading_index) != len(leading_sign):
        raise ValueError("leading index/sign 长度不一致")
    width = len(action_index)
    index: list[int] = list(leading_index)
    sign: list[int] = list(leading_sign)
    offset = len(leading_index)
    for block in range(blocks):
        base = offset + block * width
        index.extend(base + item for item in action_index)
        sign.extend(action_sign)
    return tuple(index), tuple(sign)


def _mirror(
    value: torch.Tensor, indices: tuple[int, ...], signs: tuple[int, ...]
) -> torch.Tensor:
    index = torch.tensor(indices, device=value.device)
    sign = torch.tensor(signs, dtype=value.dtype, device=value.device)
    return value[..., index] * sign


class SourceMirrorSymmetry(Symmetry):
    """镜像损失**两侧都回传梯度**（源 fork 的 PPO 口径）。"""

    def compute_loss(
        self, actor: MLPModel, batch: RolloutStorage.Batch, original_batch_size: int
    ) -> torch.Tensor:
        if not self.use_data_augmentation:
            batch.observations, _ = self.data_augmentation_func(
                env=self.env, obs=batch.observations, actions=None
            )

        assert batch.observations is not None
        mean_actions = actor(batch.observations.detach().clone())
        _, mirrored_original_actions = self.data_augmentation_func(
            env=self.env,
            obs=None,
            actions=mean_actions[:original_batch_size],
        )
        assert mirrored_original_actions is not None
        loss = F.mse_loss(
            mean_actions[original_batch_size:],
            mirrored_original_actions[original_batch_size:],
        )
        return loss if self.use_mirror_loss else loss.detach()


class SourceSymmetricPPO(PPO):
    """RSL-RL PPO using the old fork's bidirectional mirror-loss gradient."""

    def __init__(
        self,
        *args: Any,
        symmetry_cfg: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, symmetry_cfg=None, **kwargs)
        self.symmetry = SourceMirrorSymmetry(**symmetry_cfg) if symmetry_cfg else None


def mirror_obs_and_actions(
    obs: TensorDict | None,
    actions: torch.Tensor | None,
    *,
    obs_index: tuple[int, ...],
    obs_sign: tuple[int, ...],
    action_index: tuple[int, ...],
    action_sign: tuple[int, ...],
    history: int,
) -> tuple[TensorDict | None, torch.Tensor | None]:
    """把（观测, 动作）各自镜像后与原件拼在 batch 维（源 `data_augmentation_func` 口径）。

    ⚠️ actor 观测是**展平的历史**（`history × frame_dim`），而置换表是按**单帧**列号写的
    —— 必须先 reshape 回 `(-1, history, frame_dim)` 再置换，最后展平回 `(-1, history×frame)`
    （源实现就是 `reshape(-1, 10, 47)` → 索引 → `reshape(-1, 470)`；少了这一步会拿
    47 列的索引去切 470 的向量，形状静默错位）。
    """
    augmented_obs = None
    if obs is not None:
        flat = obs["actor"]
        if flat.shape[-1] != history * len(obs_index):
            raise ValueError(
                f"actor 观测展平宽度 {flat.shape[-1]} ≠ 历史 {history} × 单帧 {len(obs_index)}"
                " —— 置换表与帧布局不匹配（不许静默修剪）"
            )
        frames = flat.reshape(flat.shape[0], history, len(obs_index))
        mirrored_frame = _mirror(frames, obs_index, obs_sign)
        mirrored = obs.clone()
        mirrored["actor"] = mirrored_frame.reshape(flat.shape[0], -1)
        augmented_obs = cast(TensorDict, TensorDict.cat((obs, mirrored), dim=0))
    augmented_actions = None
    if actions is not None:
        augmented_actions = torch.cat(
            (actions, _mirror(actions, action_index, action_sign)), dim=0
        )
    return augmented_obs, augmented_actions
