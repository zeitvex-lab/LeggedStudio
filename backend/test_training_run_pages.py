"""F1/F2/F7：训练页面消费 Run 档案 —— 结构测试 + 入库反查单测。

页面是手写 HTML、没有编译期检查，这里是"下次改页面把 Run 档案区改丢 / 入库按钮
绕过后端判据"的唯一机械保障（与 E1 的 test_training_page_layers.py 同族）。
守四件事：

1. 监控详情页有「Run 档案」分区（四件套 + 对账 + 已入库产物 + 入库按钮）；
2. 入库是**走后端端点**的显式动作（页面不自带判据、不直接写 policies/）；
3. 列表页的 Run 徽章用轻量 ``?summary=1``（不拖 resolved-config/environment-lock
   两个大块——列表 5 秒一刷，拖全文就是自造卡顿）；
4. ``produced_for_run`` 能按 run_id 反查出已入库产物（供列表/详情共用）。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
LIST_PAGE = ROOT / "web" / "training_list.html"
MONITOR_PAGE = ROOT / "web" / "training_monitor.html"


class MonitorRunArchiveStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = MONITOR_PAGE.read_text(encoding="utf-8")

    def test_run_archive_section_exists_with_required_ids(self):
        positions = [self.html.find(f'id="{name}"') for name in (
            "runArchivePane", "runArchiveBody", "runArchiveList",
            "runProducedList", "runPromoteRow", "promoteBtn",
        )]
        self.assertNotIn(-1, positions, "Run 档案分区的六个锚点必须齐全")
        self.assertEqual(positions, sorted(positions), "锚点顺序：分区 → 内容 → 已入库 → 入库行 → 按钮")

    def test_archive_states_the_four_piece_vocabulary(self):
        """分区标题必须点名四件套（seed / 依赖锁 / resolved-config / 输入指纹）——
        用户看到的是"这份 Run 能否复现"，而不是一排来历不明的哈希。"""
        self.assertIn("可复现四件套", self.html)
        self.assertIn("输入指纹", self.html)

    def test_promote_goes_through_the_backend_endpoint(self):
        """入库按钮只能调 ``/api/training/{id}/promote``：判据（completed / 导出存在）
        全在后端的 promote_from_run，页面绕过它就是第二套真值。"""
        self.assertIn("/promote`", self.html, "fetch 必须打到后端 promote 端点（模板字符串）")
        self.assertIn("function promoteRun", self.html)
        self.assertIn("$('promoteBtn').addEventListener('click', promoteRun)", self.html)
        # 显式动作必须在 UI 上说清楚（训练完成不自动入库）
        self.assertIn("显式动作", self.html)

    def test_promote_visibility_follows_status_polling(self):
        """入库行可见性由状态轮询驱动（applyStatus → updatePromoteVisibility），
        且仅在档案 available 时出现——不能靠首屏一次判断定死。"""
        self.assertIn("updatePromoteVisibility", self.html)
        self.assertIn("applyStatus(status)", self.html)


class ListRunBadgeStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = LIST_PAGE.read_text(encoding="utf-8")

    def test_run_badges_render_from_backend_data(self):
        self.assertIn("async function loadRunBadges()", self.html)
        self.assertIn("function runBadges(", self.html)
        self.assertIn("runBadges(task.task_id)", self.html, "徽章必须渲染进任务行")

    def test_list_uses_summary_mode_only(self):
        """列表徽章只允许走 ``?summary=1``（不带 resolved-config/environment-lock）。
        防混装回归：哪天有人把详情版 fetch 挪进列表，5 秒一刷就是全量大 JSON。"""
        self.assertIn("/run?summary=1", self.html)
        # 不带 summary 的裸 /run 请求（单引号或反引号收尾）都不允许出现在列表页
        self.assertNotIn("'/run'", self.html)
        self.assertNotIn("`/run`", self.html)

    def test_badge_tells_verify_and_produced(self):
        """徽章必须同时回答两件事：四件套对账（档案✓/✗）与是否已入库。"""
        self.assertIn("档案✓", self.html)
        self.assertIn("档案✗", self.html)
        self.assertIn("已入库×", self.html)


class ProducedForRunTest(unittest.TestCase):
    def test_reverse_lookup_by_run_id(self):
        from backend import policy_artifacts as pa
        from backend.training.runs import create_run_for_task
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "task_x"
            contract = SimpleNamespace(robot_id="unitree_go2", compute_hash=lambda: "cafe1234")
            create_run_for_task(run_dir, contract=contract,
                                config={"robot_id": "unitree_go2", "seed": 1}, task="training")
            (run_dir / "status.json").write_text(
                json.dumps({"status": "train_completed", "max_iterations": 5}), encoding="utf-8")
            (run_dir / "exported").mkdir()
            (run_dir / "exported" / "policy.onnx").write_bytes(b"blob")
            out = root / "policies"
            artifact = pa.promote_from_run(run_dir, out_dir=out)

            found = pa.produced_for_run(run_dir.name, out_dir=out)
            self.assertEqual([artifact["artifact_id"]], [p["artifact_id"] for p in found])
            self.assertEqual(artifact["onnx_sha256"], found[0]["onnx_sha256"])

            # 别的 run_id 一条都不该返回；空 run_id 同样（防御）
            self.assertEqual([], pa.produced_for_run("no-such-run", out_dir=out))
            self.assertEqual([], pa.produced_for_run("", out_dir=out))


if __name__ == "__main__":
    unittest.main()
