"""H6：`adapters/nav_ros2` 接口占位的四条锁（**测试放在 backend/ 是为了被 discover 跑到**：
`adapters/test_*.py` 不在 `unittest discover -s backend` 的范围内）。

守什么：

1. **借来的每个参数值都能回真源核对** —— `BORROWED_PARAMS` 里记的 (源, 值) 必须在那个源 YAML 的
   对应键行上真的存在。这条是 H6 唯一的实质判据："只借参数"如果连出处都核不上，就只是抄了个数字。
2. **分歧必须如实登记，不许取平均** —— `agreement` 字段必须与 `sources` 的实际取值一致
   （多值相同 ⇒ consistent，不同 ⇒ disagree）。三个参考源本就不是一套栈：`slam_nav2` /
   `rc_competition` 用 DWB，`go2_nav` 用 MPPI，`use_astar` 两源 false、一源 true。
3. **对照 ≠ 真值** —— 每项都必须写 `our_truth`（本仓真值在哪；没有对应物就明说"无对应物"）。
   否则几个月后这些 Nav2 数字会被当成我们的取值照搬（本仓 0.2 m vs Nav2 0.5 m 就是实例）。
4. **不引运行时** —— 导入本包不得把 `rclpy` 拉进 `sys.modules`，"接口占位"不许变成隐形依赖。

**2026-09-20 实测订正**：H6 的说明把 `controller_frequency 10 / max_vel_x 0.6 / max_vel_theta 2.0 /
use_astar` 标为来自 `unitree-go2-slam-nav2` 与 `unitree_go2_nav` 的"互校"——**归属错了**：
那组数字实际出自第三个源 `rc_old/.../sim2real_nav2`（比赛栈），而前两个源分别是 20.0 / 0.15 /
1.0 / false。本模块按**实际出处**登记，并把三源差异一并记下来。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.nav_ros2 import interface as nav_iface  # noqa: E402


def _yaml_lines(source: str) -> list[str]:
    path = ROOT / nav_iface.PARAM_SOURCES[source]
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _render(value: object) -> str:
    """Python 值 → YAML 里的字面量（bool 是 int 子类，必须先判）。"""

    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class DeclarationShapeTest(unittest.TestCase):
    def test_stable_shape(self):
        described = nav_iface.describe()
        self.assertEqual("nav-ros2-interface-1.0", described["schema"])
        for key in ("external_stack", "borrowed_params", "not_migrated", "telemetry_fields", "availability"):
            self.assertIn(key, described)
        for group, fields in (
            (nav_iface.EXTERNAL_STACK, ("id", "label", "role", "status", "reference", "note")),
            (nav_iface.BORROWED_PARAMS, ("name", "yaml_key", "sources", "agreement", "our_truth", "note")),
            (nav_iface.NOT_MIGRATED, ("id", "what", "why")),
            (nav_iface.TELEMETRY_FIELDS, ("id", "label", "level", "owner", "shape", "note")),
        ):
            ids = [item["id" if "id" in item else "name"] for item in group]
            self.assertEqual(len(ids), len(set(ids)), f"重复条目：{ids}")
            for item in group:
                for field in fields:
                    self.assertTrue(str(item.get(field) or "").strip(), f"{ids} 缺 {field}")

    def test_not_migrated_is_explicit(self):
        """不搬的东西必须写明理由（否则下一个人会"顺手"搬进来）。"""

        ids = {item["id"] for item in nav_iface.NOT_MIGRATED}
        self.assertLessEqual({"nav2_full", "odin_driver", "habitat_vlm", "gpu_raycast"}, ids)
        for item in nav_iface.NOT_MIGRATED:
            self.assertGreater(len(item["why"]), 10, f"{item['id']} 的理由太短，等于没说")


class BorrowedParamProvenanceTest(unittest.TestCase):
    """核心判据：借来的值必须能在真源 YAML 上找到（逐源逐值，不是抽一个看）。"""

    def setUp(self):
        present = {
            name: (ROOT / relative).is_file() for name, relative in nav_iface.PARAM_SOURCES.items()
        }
        if not any(present.values()):
            self.skipTest(f"参考源不在（未同步 00_resources）：{present}")

    def test_every_recorded_value_exists_in_its_source(self):
        checked = 0
        for param in nav_iface.BORROWED_PARAMS:
            for source, value in param["sources"].items():
                lines = _yaml_lines(source)
                if not lines:
                    continue  # 该源未同步：跳过这一源，但下面的计数会反映实际核对量
                expected = re.compile(
                    rf"^\s*{re.escape(param['yaml_key'])}:\s*{re.escape(_render(value))}\s*(?:#.*)?$"
                )
                self.assertTrue(
                    any(expected.match(line) for line in lines),
                    f"{param['name']} 在 {source} 上找不到 `{param['yaml_key']}: {_render(value)}`"
                    f"（源：{nav_iface.PARAM_SOURCES[source]}）",
                )
                checked += 1
        self.assertGreaterEqual(checked, 10, f"实际核对的 (参数, 源) 组合太少：{checked}")

    def test_agreement_flag_matches_the_data(self):
        """`agreement` 不许与数据脱节：多值相同 ⇒ consistent，不同 ⇒ disagree。"""

        for param in nav_iface.BORROWED_PARAMS:
            distinct = {_render(value) for value in param["sources"].values()}
            expected = "consistent" if len(distinct) == 1 else "disagree"
            self.assertEqual(
                expected, param["agreement"],
                f"{param['name']} 的 agreement={param['agreement']!r} 与取值 {sorted(distinct)} 不符"
                "（分歧必须如实登记，不许取平均或只留一个）",
            )

    def test_no_source_is_silently_dropped(self):
        """不许静默丢源：源 YAML 里**有**这个键 ⇒ 必须登记该源的值；**没有**该键 ⇒ 不许登记。

        这条才是"互校"的实质：三个源不是一套栈（`go2_nav` 用 MPPI，没有 DWB 的 `max_vel_x` /
        `PathAlign.scale`），所以"某个源没有这个键"必须由数据本身说清，而不是靠人记得。
        写法上刻意不查注释措辞——**查数据**，免得测试变成格式审查。
        """

        checked = 0
        for param in nav_iface.BORROWED_PARAMS:
            for source in nav_iface.PARAM_SOURCES:
                lines = _yaml_lines(source)
                if not lines:
                    continue
                has_key = any(
                    re.match(rf"^\s*{re.escape(param['yaml_key'])}:", line) for line in lines
                )
                recorded = source in param["sources"]
                if has_key:
                    self.assertTrue(
                        recorded,
                        f"{param['name']}：{source} 的 YAML 里有 `{param['yaml_key']}`，却没登记该源的值"
                        f"（源：{nav_iface.PARAM_SOURCES[source]}）",
                    )
                    checked += 1
                else:
                    self.assertFalse(
                        recorded,
                        f"{param['name']}：{source} 的 YAML 里没有 `{param['yaml_key']}`，不该登记它的值",
                    )
        self.assertGreaterEqual(checked, 8, f"实际核对到的 (参数, 源) 组合太少：{checked}")

    def test_disagreeing_params_explain_themselves(self):
        """登记为 disagree 的项，note 必须真的解释分歧（不是留一句"见上"）。"""

        disagreeing = [p for p in nav_iface.BORROWED_PARAMS if p["agreement"] == "disagree"]
        self.assertTrue(disagreeing, "三个源本就不是一套栈，应当存在登记为 disagree 的参数")
        for param in disagreeing:
            self.assertGreaterEqual(len(param["sources"]), 2, f"{param['name']} 应至少有两个源")
            self.assertGreater(
                len(param["note"]), 10, f"{param['name']} 的分歧没解释清楚：{param['note']!r}"
            )

    def test_every_param_declares_our_truth(self):
        """对照 ≠ 真值：每项都要写清本仓真值在哪（没有对应物就明说）。"""

        for param in nav_iface.BORROWED_PARAMS:
            self.assertTrue(param["our_truth"].strip(), f"{param['name']} 缺 our_truth")


class NoRuntimeDependencyTest(unittest.TestCase):
    def test_importing_the_placeholder_does_not_pull_ros2(self):
        """"接口占位"不许变成隐形依赖：导入后 `rclpy` 不得出现在 sys.modules。"""

        self.assertNotIn("rclpy", sys.modules)
        self.assertIs(False, nav_iface.availability()["runtime_required"])
        self.assertIs(False, nav_iface.availability()["connected"])

    def test_availability_is_honest_and_total(self):
        """可用性查询不许抛（ROS2 没装是**正常状态**，不是异常）。"""

        available = nav_iface.availability()
        self.assertIsInstance(available["ros2_importable"], bool)
        self.assertEqual(set(nav_iface.PARAM_SOURCES), set(available["reference_sources_present"]))


class TelemetryCoverageTest(unittest.TestCase):
    def test_levels_and_owners_are_declared(self):
        levels = {field["level"] for field in nav_iface.TELEMETRY_FIELDS}
        self.assertLessEqual({"D2", "D3", "D4"}, levels, "D2–D4 的遥测必须有字段（对齐 06 §4.3）")
        owners = {field["owner"] for field in nav_iface.TELEMETRY_FIELDS}
        self.assertLessEqual(owners, {"external", "repo"}, f"owner 只许 external/repo：{owners}")
        self.assertIn("external", owners, "外部栈该报什么，是本接口存在的理由")
        self.assertIn("repo", owners, "本仓已有的等价物也要登记，免得重复实现")

    def test_repo_owner_notes_name_real_files(self):
        """`owner=repo` 的"本仓已有"必须点名**真实存在**的文件（改路径即红，防声明腐化）。"""

        path_pattern = re.compile(r"(?:backend|adapters|web|registry|contracts|tools|scripts)/[\w./-]+\.\w+")
        checked = 0
        for field in nav_iface.TELEMETRY_FIELDS:
            if field["owner"] != "repo":
                continue
            found = path_pattern.findall(field["note"])
            self.assertTrue(found, f"{field['id']} 标为 repo 已有，却没点名任何文件：{field['note']}")
            for relative in found:
                self.assertTrue((ROOT / relative).is_file(), f"{field['id']} 点名的 {relative} 不存在")
                checked += 1
        self.assertGreaterEqual(checked, 3, f"实际核对到的 repo 文件太少：{checked}")

    def test_borrowed_param_truth_paths_also_exist(self):
        """`our_truth` 里点名的本仓文件同样要真实存在（否则真值链是画上去的）。"""

        path_pattern = re.compile(r"(?:backend|adapters|web|registry|contracts|tools|scripts)/[\w./-]+\.\w+")
        for param in nav_iface.BORROWED_PARAMS:
            for relative in path_pattern.findall(param["our_truth"]):
                self.assertTrue((ROOT / relative).is_file(), f"{param['name']} 的真值路径 {relative} 不存在")


if __name__ == "__main__":
    unittest.main()
