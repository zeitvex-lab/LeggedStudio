"""Go2 的 runner 类（薄委托：族级 Skills 的 runner 实现 + 本机型部署契约元数据）。

族级实现：`adapters/mjlab/kits/quadruped_kit/skills/velocity/runner.py`。本模块只剩
两样 go2 事实：

1. **部署契约元数据** `go2_policy_contract_metadata`（`deploy/policy.py`）——
   族级 runner 通过 `policy_metadata_fn` 注入件调用它（技能层不 import 机型包）；
2. **两台 runner 类**（`VelocityOnPolicyRunner` / `VelocityDistillationRunner`）——
   类名与 `entrypoints.runner_class` 不变，只把"机型侧注入件"挂上去：
   * `policy_metadata_fn` = go2 的部署契约元数据；
   * `skip_onnx_export_env_var` = `GO2_SKIP_ONNX_EXPORT`（原实况：大规模并行验证
     跑可以关掉 ONNX 导出而保留 .pt）。

原先本文件 417 行里的 runner 机制（checkpoint 归一化重建、min_std 补齐、条件策略
推理路径、循环学生蒸馏循环与 teacher checkpoint 加载、ONNX/recurrent 导出）已整段
上移为族级实现。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与 `training/config.py` 同一约定）。
for _parent in Path(__file__).resolve().parents:
  if (_parent / "adapters" / "mjlab").is_dir():
    if str(_parent) not in sys.path:
      sys.path.insert(0, str(_parent))
    break

from adapters.mjlab.kits.quadruped_kit.skills.velocity import runner as kit_runner  # noqa: E402

from ..deploy.policy import go2_policy_contract_metadata  # noqa: E402


class VelocityOnPolicyRunner(kit_runner.VelocityOnPolicyRunner):
  """Go2 的 on-policy runner（族级实现 + 本机型部署契约元数据）。"""

  policy_metadata_fn = staticmethod(go2_policy_contract_metadata)
  skip_onnx_export_env_var = "GO2_SKIP_ONNX_EXPORT"


class VelocityDistillationRunner(kit_runner.VelocityDistillationRunner):
  """Go2 的循环学生蒸馏 runner（族级实现 + 本机型部署契约元数据）。"""

  policy_metadata_fn = staticmethod(go2_policy_contract_metadata)
  skip_onnx_export_env_var = "GO2_SKIP_ONNX_EXPORT"


__all__ = ["VelocityDistillationRunner", "VelocityOnPolicyRunner"]
