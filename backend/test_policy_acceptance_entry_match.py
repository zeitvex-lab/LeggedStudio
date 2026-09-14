"""验收脚本的**策略条目匹配**：``--policy`` 必须对回它自己的声明。

背景（B10 收尾遗留缺陷）：B10 删掉 46 处裸 ``path``/``url`` 后，
``adapters/mjlab/policy_acceptance.py`` 的旧匹配 ``p.get("path", "")`` 恒为空串；
而实测 46 条声明中 **45 条文件名 stem ≠ id**，于是 ``/api/simulation/policies/acceptance``
几乎每次都静默回落 ``policies[0]`` —— **拿第一条策略的增益/观测布局去验收别的策略**
（"看起来生效、实际不生效"同族；契约条目缺位正是零力矩缺陷的形态）。

修法：匹配统一走 ``match_policy_entry``（先按 id，再按解析出的 blob 文件名**全等**），
``tools/sim2sim_headless.py`` 复用同一实现。这里守四件事：

1. 真实包数据：每条声明的解析路径必须能对回**它自己**（防声明/索引漂移）；
2. 旧 bug 的反例：按文件名匹配不得返回 ``policies[0]``（go2 的 go2-moe-cts 案例）；
3. fail-closed：对不上返回 ``None``，不猜条目；
4. ``endswith`` 后缀误配（``mypolicy.onnx`` vs ``policy.onnx``）不复发。
"""

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

from backend.policy_artifacts import policy_relative_path

ROOT = Path(__file__).resolve().parents[1]


def load_engine():
    """按文件位置加载 ``policy_acceptance``（它不是包成员；顶层只依赖 numpy）。"""
    spec = importlib.util.spec_from_file_location(
        "policy_acceptance_for_entry_match_test",
        ROOT / "adapters" / "mjlab" / "policy_acceptance.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MatchPolicyEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.engine = load_engine()

    # ---------- 真实包数据 ----------

    def test_every_declared_policy_matches_itself(self):
        """全仓每条声明：用解析出的路径反查，必须命中**同一条**声明。

        这是防漂移不变量：声明只留 id 后，路径真值在 ``policies/index.json``；
        索引与声明一旦分叉（改了 id 没改索引、或反之），这里立刻红。
        例外如实放行：**共用同一 onnx 的多条声明**（lite3 两条，已登记的重复声明）
        在文件名匹配原理上分不出谁是谁 —— 只要求命中**同 blob** 的声明，
        消歧必须走 ``--policy-id``（有专项测试）。
        """
        robots = ROOT / "assets" / "robots"
        checked = ambiguous = 0
        for pkg in sorted(robots.iterdir()):
            cfg_path = pkg / "simulation" / "config.json"
            if not cfg_path.is_file():
                continue
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            policies = [p for p in (cfg.get("policies") or []) if isinstance(p, dict)]
            for entry in policies:
                rel = policy_relative_path(entry, robot_dir=pkg)
                if not rel:
                    continue  # 包外/无 blob 的声明（如 demo 素材）不在验收范围
                matched = self.engine.match_policy_entry(policies, pkg / rel, pkg)
                self.assertIsNotNone(matched, f"{pkg.name}: {entry.get('id')} 解析出 {rel} 却匹配不回任何声明")
                if matched.get("id") == entry.get("id"):
                    checked += 1
                    continue
                self.assertEqual(
                    rel, policy_relative_path(matched, robot_dir=pkg),
                    f"{pkg.name}: {entry.get('id')} 与 {matched.get('id')} 既非同 id 也非同 blob —— 匹配错人",
                )
                ambiguous += 1
        self.assertGreater(checked, 35, "前置失效：真实包应至少覆盖 35 条无歧义声明")
        self.assertLessEqual(ambiguous, 3, "共用 blob 的声明超出已知集合（lite3×2），应先处理数据再放宽")

    def test_filename_match_does_not_fall_back_to_first(self):
        """旧 bug 的直接反例：go2 按 ``go2_moe_cts.onnx`` 匹配，不得拿到 policies[0]。

        go2 的 policies[0] 是 ``go2-backflip-69``（模仿任务，增益/观测布局完全不同）。
        """
        pkg = ROOT / "assets" / "robots" / "unitree_go2"
        cfg = json.loads((pkg / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        policies = [p for p in (cfg.get("policies") or []) if isinstance(p, dict)]
        target = next(p for p in policies if p.get("id") == "go2-moe-cts")
        rel = policy_relative_path(target, robot_dir=pkg)
        self.assertTrue(rel, "前置：go2-moe-cts 可解析出包内路径")

        matched = self.engine.match_policy_entry(policies, pkg / rel, pkg)

        self.assertEqual("go2-moe-cts", matched.get("id"))
        self.assertNotEqual(policies[0].get("id"), matched.get("id"), "不得静默回落 policies[0]")

    # ---------- 合成用例（fail-closed / 匹配语义） ----------

    def _synthetic(self, tmp: str, policies: list[dict]) -> tuple[pathlib.Path, list[dict]]:
        pkg = pathlib.Path(tmp) / "robot_x"
        (pkg / "simulation" / "policies").mkdir(parents=True)
        (pkg / "simulation" / "config.json").write_text(
            json.dumps({"policies": policies}, ensure_ascii=False), encoding="utf-8",
        )
        for name in ("policy.onnx", "mypolicy.onnx", "himloco_velocity_hist6.onnx"):
            (pkg / "simulation" / "policies" / name).write_bytes(b"onnx-blob")
        return pkg, policies

    def test_no_match_returns_none(self):
        """对不上任何声明 → None（fail-closed），由调用方决定报错，不猜条目。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg, policies = self._synthetic(tmp, [{"id": "alpha", "path": "simulation/policies/policy.onnx"}])
            unknown = pkg / "simulation" / "policies" / "elsewhere.onnx"
            self.assertIsNone(self.engine.match_policy_entry(policies, unknown, pkg))

    def test_id_match_takes_priority(self):
        """``--policy <id>`` 约定：stem 恰为声明 id 时按 id 命中（文件可以不存在）。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg, policies = self._synthetic(tmp, [{"id": "alpha", "path": "simulation/policies/policy.onnx"}])
            by_id = pkg / "alpha"  # 不存在的路径，stem == 声明 id
            matched = self.engine.match_policy_entry(policies, by_id, pkg)
            self.assertIsNotNone(matched)
            self.assertEqual("alpha", matched.get("id"))

    def test_policy_id_disambiguates_shared_blob(self):
        """共用同一 onnx 的两条声明（lite3 实况）：``--policy-id`` 必须分得出谁是谁。

        这是验收端点的真实链路（``simulation_api`` 现在显式传 ``--policy-id``）：
        文件名匹配原理上分不出 benchmark/sdk45，只能靠 id。
        """
        with tempfile.TemporaryDirectory() as tmp:
            shared = "simulation/policies/himloco_velocity_hist6.onnx"
            policies = [
                {"id": "lite3-velocity-benchmark", "path": shared},
                {"id": "lite3-velocity-sdk45", "path": shared},
            ]
            pkg, policies = self._synthetic(tmp, policies)
            blob = pkg / shared
            self.assertEqual(
                "lite3-velocity-benchmark",
                self.engine.match_policy_entry(policies, blob, pkg).get("id"),
                "不带 id 时按声明顺序取第一条（如实、可复现）",
            )
            self.assertEqual(
                "lite3-velocity-sdk45",
                self.engine.match_policy_entry(policies, blob, pkg, "lite3-velocity-sdk45").get("id"),
            )
            # 显式 id 对不上时**不得**退回文件名匹配 —— 调用方点名了要谁，
            # 给别人属于答非所问。
            self.assertIsNone(self.engine.match_policy_entry(policies, blob, pkg, "no-such-id"))

    def test_basename_equality_not_endswith(self):
        """文件名**全等**匹配：``mypolicy.onnx`` 不得被 ``--policy policy.onnx`` 吸走。

        旧实现（sim2sim_headless 第一版）用 ``endswith``：wuji_hand 的 blob 恰叫
        ``policy.onnx``，后缀匹配会把同名后缀的兄弟文件误配进来。
        """
        with tempfile.TemporaryDirectory() as tmp:
            pkg, policies = self._synthetic(tmp, [
                {"id": "alpha", "path": "simulation/policies/policy.onnx"},
                {"id": "beta", "path": "simulation/policies/mypolicy.onnx"},
            ])
            want_alpha = pkg / "simulation" / "policies" / "policy.onnx"
            matched = self.engine.match_policy_entry(policies, want_alpha, pkg)
            self.assertEqual("alpha", matched.get("id"))

            want_beta = pkg / "simulation" / "policies" / "mypolicy.onnx"
            matched = self.engine.match_policy_entry(policies, want_beta, pkg)
            self.assertEqual("beta", matched.get("id"))


if __name__ == "__main__":
    unittest.main()
