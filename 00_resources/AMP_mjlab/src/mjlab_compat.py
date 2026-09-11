"""mjlab 1.6 兼容层（本仓库原基于 mjlab 1.2.0）。

平台统一运行时为 mjlab 1.6.0（adapters/mjlab/.venv）。本模块补齐 1.2.0 中存在、
1.6.0 中缺失/变更的两处能力，导入本模块即完成补丁（幂等）：

1. ``mjlab.utils.os.update_assets``：把资产目录读入 ``{相对路径: bytes}`` 字典，
   供 ``MjSpec.assets`` 使用。1.6.0 已从 ``mjlab.utils.os`` 移除。
2. ``ObservationGroupCfg(history_ordering="time")``：时间主序历史观测。
   原实现见 ``mjlab_patch/mjlab/managers/observation_manager.py``（针对 1.2.0 的
   整文件替换）；此处改为运行时猴子补丁，语义与其一致：
   - 组内每个 term 的历史不展平（buffer 形状 (N, H, D)）；
   - 组内 cat 后得到 (N, H, ΣD)，再 reshape 为 (N, H*ΣD)，时间维在外层交错。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mjlab.managers.observation_manager as _om
import mjlab.utils.os as _mj_os


##
# 1. update_assets（1.2.0 API，1.6.0 移除）
#
def _update_assets(assets: dict[str, bytes], src_dir: Path, meshdir: str) -> None:
  """Recursively read files from ``src_dir`` into ``assets``.

  Keys follow MuJoCo asset-dict convention: ``meshdir + relative path``.
  """
  src_dir = Path(src_dir)
  for file in sorted(src_dir.rglob("*")):
    if not file.is_file():
      continue
    key = f"{meshdir}/{file.relative_to(src_dir).as_posix()}"
    assets[key] = file.read_bytes()


if not hasattr(_mj_os, "update_assets"):
  _mj_os.update_assets = _update_assets

# 供 try/except ImportError 回退导入（g1_constants*.py）。
update_assets = _update_assets


##
# 2. history_ordering="time"（原 mjlab_patch 功能）
#
def _patch_observation_group_cfg() -> None:
  original_init = _om.ObservationGroupCfg.__init__

  def init(self: Any, *args: Any, history_ordering: str = "term", **kwargs: Any) -> None:
    original_init(self, *args, **kwargs)
    if history_ordering not in ("term", "time"):
      raise ValueError(
        f"history_ordering must be 'term' or 'time', got {history_ordering!r}"
      )
    self.history_ordering = history_ordering

  _om.ObservationGroupCfg.__init__ = init


def _patch_observation_manager() -> None:
  manager = _om.ObservationManager
  original_prepare = manager._prepare_terms
  original_compute_group = manager.compute_group

  def prepare_terms(self: Any) -> None:
    # time-major：term 历史保持 (N, H, D) 不展平，cat 后统一 reshape。
    for group_cfg in self.cfg.values():
      if getattr(group_cfg, "history_ordering", "term") != "time":
        continue
      if group_cfg.history_length is None:
        continue
      for term_cfg in group_cfg.terms.values():
        term_cfg.flatten_history_dim = False
    original_prepare(self)

  def compute_group(self: Any, group_name: str, update_history: bool = False, *args: Any, **kwargs: Any):
    result = original_compute_group(self, group_name, update_history, *args, **kwargs)
    group_cfg = self.cfg[group_name]
    if (
      getattr(group_cfg, "history_ordering", "term") == "time"
      and isinstance(result, __import__("torch").Tensor)
      and result.dim() == 3
    ):
      result = result.reshape(result.shape[0], -1)
    return result

  manager._prepare_terms = prepare_terms
  manager.compute_group = compute_group


_patched = getattr(_om, "_amp_mjlab_16_compat_applied", False)
if not _patched:
  _patch_observation_group_cfg()
  _patch_observation_manager()
  _om._amp_mjlab_16_compat_applied = True
