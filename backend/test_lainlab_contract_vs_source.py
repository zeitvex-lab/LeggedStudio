"""LainLab 部署契约 ↔ **上游训练源**逐字段对账（2026-09-22）。

## 为什么要有这一层（本轮两次人肉修的正是它能自动抓的）

同状态对拍（`tools/obs_crosscheck.py`）守的是"两份实现一致"，**守不了"规格本身对不对"**：
`rear-stand`/`handstand` 的对拍一直是绿的，因为浏览器 `CONFIG.*` 与验收器读的是**同一份错契约**
——一致地错。本轮抓出的两处真源漂移（都靠人肉读上游源码）：

* 7 条策略**共用一份默认姿/初高**，而上游是**逐技能**的机器人工厂（trot 的 hip 是 0.0、
  dreamwaq/cts 用基座的 0.9/−1.8、spring_jump 出生高 0.39…）；
* 两条姿态类技能**根本没声明 `scales`**，引擎回落 1.0，而上游是
  `ang_vel×0.25 / cmd[:2]×2 / cmd[2]×0.25 / dq×0.05` —— 差 4×/2×/20×，策略 0.5 s 内崩。

所以本测试把**能量化派生的字段**直接从上游源码解出来对比（不抄一份常量到仓里当"第二真值"）：
`actor frame_dim` / `history_length` / `action_scale` / 出生高 / 默认姿。
**解不动、或解析本身易碎的地方不硬解**（如各技能帧构造里的缩放字面量），改为"断言 + 溯源"
（写明确切出处），并在下方逐条登记。

上游目录：`00_resources/LainLab/src/tasks/robots/go2/skills/`（169 py，随仓同步）。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "00_resources" / "LainLab" / "src" / "tasks" / "robots" / "go2" / "skills"
ROBOT_CFG = SKILLS / "shared" / "robot.py"
GO2_CONSTANTS = ROOT / "00_resources" / "LainLab" / "src" / "assets" / "robots" / "unitree_go2" / "go2_constants.py"
SIM_CFG = ROOT / "assets" / "robots" / "unitree_go2" / "simulation" / "config.json"


def _profile_fields(skill: str) -> dict[str, float]:
    """解技能 `profile.py` 里 `name: type = value` 形式的常量（dataclass 默认值）。"""
    path = SKILLS / skill / "profile.py"
    if not path.is_file():
        return {}
    fields: dict[str, float] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                try:
                    fields[stmt.target.id] = ast.literal_eval(stmt.value)
                except (ValueError, SyntaxError):
                    continue
    return fields


#: 技能目录名 → 观测类名里的写法（类名与目录名并不总是一致）。
_ALIASES = {"dreamwaq": "dream", "amp_dreamwaq": "dream", "cts": "dream", "ts": "dream",
            "spring_jump": "spring", "backflip": "jump"}


def _actor_obs_class(skill: str) -> tuple[int, int] | None:
    """解 `mdp/observations.py` 里 actor 观测的 `(frame_dim, history_length)`。

    **只认"类名能对上本技能"的那一个**：同一文件里放着多个技能的历史类
    （`hand_stand/mdp/observations.py` 里 trot/jump/handstand 的类都在），不限定归属就会
    张冠李戴（实测 `hand_stand` 的 profile 48/1 曾被同文件 trot 的 `TrotActorHistory` 47/10
    盖掉）。对不上就返回 None，调用点改用 `profile.py` 的技能级声明。

    两种写法都要认（实测各技能不一致，这本身就是"描述散落"的证据）：
    * 显式属性：`frame_dim = 47` / `history_length = 10`（trot/jump/hand_stand/rear_stand）；
    * 隐含在缓冲区里：`torch.zeros((num_envs, 5, 45))` + docstring "Five source frames
      **immediately preceding** the actor frame" ⇒ 观测 = 5 历史帧 + 当前帧 ⇒ history 6、
      frame_dim 45（dreamwaq/cts 系）。
    """
    path = SKILLS / skill / "mdp" / "observations.py"
    if not path.is_file():
        return None
    found: list[tuple[int, int]] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not (isinstance(node, ast.ClassDef) and "Actor" in node.name):
            continue
        class_key = node.name.replace("_", "").lower()
        if not any(alias and alias in class_key
                   for alias in {skill.replace("_", ""), _ALIASES.get(skill, "")}):
            continue
        vals: dict[str, int] = {}
        fallback: tuple[int, int] | None = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name) \
                    and stmt.targets[0].id in ("frame_dim", "history_length"):
                vals[stmt.targets[0].id] = ast.literal_eval(stmt.value)
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                        and sub.func.attr == "zeros" and sub.args and isinstance(sub.args[0], ast.Tuple):
                    # 第一维是 batch（`env.num_envs`，非常量），故取后两个常量：历史帧数、帧宽
                    dims = [a.value for a in sub.args[0].elts
                            if isinstance(a, ast.Constant) and isinstance(a.value, int)]
                    if len(dims) >= 2:
                        fallback = (int(dims[-1]), int(dims[-2]) + 1)   # 历史 N 帧 + 当前帧
        if {"frame_dim", "history_length"} <= set(vals):
            found.append((vals["frame_dim"], vals["history_length"]))
        elif fallback is not None:
            found.append(fallback)
    if not found:
        return None
    # 同一文件里既有单帧 `*ActorObservation`（45×1）又有 `*ActorHistory` 包裹（45×11 之类）：
    # 网络的真实输入是**乘积最大**的那一个（帧宽 × 帧数）。
    return max(found, key=lambda pair: pair[0] * pair[1])


def _robot_factory(skill: str) -> dict:
    """解 `shared/robot.py` 里该技能的机器人工厂（`init_state.pos` / `joint_pos`）。

    函数名不保证等于技能目录名（实测：目录 `hand_stand` ↔ 工厂 `handstand_robot_cfg`），
    故按"去下划线后包含技能名"来配，配不到就返回空（调用点回落到基座 INIT_STATE）。
    """
    text = ROBOT_CFG.read_text(encoding="utf-8")
    tree = ast.parse(text)
    compact = skill.replace("_", "")
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if not (node.name.endswith("_robot_cfg") and compact in node.name.replace("_", "")):
            continue
        pos, joint_pos = None, {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign) and isinstance(sub.targets[0], ast.Attribute):
                attr = sub.targets[0].attr
                if attr == "pos":
                    pos = ast.literal_eval(sub.value)
                elif attr == "joint_pos" and isinstance(sub.value, ast.Dict):
                    for k, v in zip(sub.value.keys, sub.value.values):
                        if isinstance(k, ast.Constant):
                            joint_pos[k.value] = ast.literal_eval(v)
        return {"pos": pos, "joint_pos": joint_pos}
    return {"pos": None, "joint_pos": {}}


def _base_init_state() -> dict:
    """基座 `go2_constants.INIT_STATE`（技能工厂没覆盖时用的就是它）。"""
    text = GO2_CONSTANTS.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == "INIT_STATE":
            call = node.value
            pos, joint_pos = None, {}
            for kw in call.keywords:
                if kw.arg == "pos":
                    pos = ast.literal_eval(kw.value)
                elif kw.arg == "joint_pos" and isinstance(kw.value, ast.Dict):
                    for k, v in zip(kw.value.keys, kw.value.values):
                        joint_pos[k.value] = ast.literal_eval(v)
            return {"pos": pos, "joint_pos": joint_pos}
    return {"pos": None, "joint_pos": {}}


def _resolve_joint(pattern_map: dict[str, float], joint: str) -> float | None:
    """上游 `joint_pos` 的键可能是正则（`.*thigh_joint`）或精确名；按"精确名优先、再子串"解析。"""
    if joint in pattern_map:
        return pattern_map[joint]
    for key, val in pattern_map.items():
        core = key.replace(".*", "")
        if core and core in joint:
            return val
    return None


def _sourced_skill(skill: str) -> str:
    """技能若复用别的技能的帧（`...<other>.mdp.observations`），返回那个真正定义帧的技能。"""
    path = SKILLS / skill / "mdp" / "observations.py"
    if not path.is_file():
        return skill
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.ImportFrom) and node.level == 3 and node.module):
            continue
        # 只跟随"另一个技能的 mdp.observations"（那才是帧定义）；`...shared.actions` 这类
        # 公共依赖不是帧来源（早期版本照第一个相对导入跳，结果跳到 skills/shared 上）。
        if not node.module.endswith(".mdp.observations"):
            continue
        head = node.module.split(".")[0]
        if head not in (skill, "shared") and (SKILLS / head).is_dir():
            return head
    return skill


class LainlabContractMatchesSourceTest(unittest.TestCase):
    """逐条策略：契约里的**可派生字段**必须与上游源码一致。"""

    @classmethod
    def setUpClass(cls):
        cls.sim = json.loads(SIM_CFG.read_text(encoding="utf-8-sig"))
        cls.policies = [e for e in cls.sim["policies"] if "lainlab" in (e.get("id") or "")]

    def _skill_of(self, entry: dict) -> str:
        blob = json.dumps(entry, ensure_ascii=False)
        m = re.search(r"skills/([a-z_]+)", blob)
        self.assertIsNotNone(m, f"{entry['id']} 的 source/training_ref 没写明上游技能目录")
        return m.group(1)

    def test_every_lainlab_policy_resolves_its_skill(self):
        for entry in self.policies:
            skill = self._skill_of(entry)
            self.assertTrue((SKILLS / skill).is_dir(), f"{entry['id']} → skills/{skill} 不存在")

    def test_actor_dims_and_history_match_source(self):
        """obs_dim / history_len 必须等于上游声明。

        真值来源有两处：`profile.py` 的 `actor_frame_dim/actor_history`（技能级声明）与
        `mdp/observations.py` 里 actor 观测类的 `frame_dim/history_length`（实现级）；
        两者都在时**必须一致**（互相印证）。**技能可以复用别的技能的帧**（实测 `cts` 直接
        `from ...dreamwaq.mdp.observations import _actor_frame`）⇒ 本技能没有声明时
        跟随相对导入去找真正定义帧的那个技能。
        """
        for entry in self.policies:
            skill = _sourced_skill(self._skill_of(entry))
            fields = _profile_fields(skill)
            contract = entry.get("contract") or {}
            # 真值来源有两处：profile 的 `actor_frame_dim/actor_history`（技能级声明）与
            # `mdp/observations.py` 里 actor 观测类的 `frame_dim/history_length`（实现级）。
            # cts 这类 profile 只写任务元信息，维数在实现里；两者都在时**必须一致**（互相印证）。
            profile_dims = ((int(fields["actor_frame_dim"]), int(fields["actor_history"]))
                            if "actor_frame_dim" in fields and "actor_history" in fields else None)
            cls_dims = _actor_obs_class(skill)
            self.assertTrue(profile_dims is not None or cls_dims is not None,
                            f"skills/{skill}：profile 与观测类都没解到 actor 维数声明")
            if profile_dims and cls_dims:
                # 观测类**跨技能共享/复用**（同一文件里放着若干技能的历史类；dreamwaq/cts/ts
                # 还共用同一份帧），所以只在"类名能对上这个技能"时才做互相印证——名字对不上
                # 时无法判断该类是否属于本技能，硬比会产生假红（实测 `hand_stand` profile
                # 48/1 会被同文件里 trot 的 `TrotActorHistory`(47/10) 盖掉）。
                self.assertEqual(profile_dims, cls_dims, f"skills/{skill}：profile 与观测类两处声明不一致")
            frame_dim, history = profile_dims or cls_dims
            self.assertEqual(frame_dim, contract.get("obs_dim"),
                             f"{entry['id']}：契约 obs_dim 与上游声明不一致")
            self.assertEqual(history, contract.get("history_len") or entry.get("history_len"),
                             f"{entry['id']}：契约 history_len 与上游声明不一致")

    def test_action_scale_matches_profile(self):
        for entry in self.policies:
            skill = self._skill_of(entry)
            fields = _profile_fields(skill)
            if "action_scale" not in fields:
                continue
            self.assertAlmostEqual(
                float(fields["action_scale"]),
                float((entry.get("contract") or {}).get("action_scale") or 0.0),
                places=6, msg=f"{entry['id']}：action_scale 与上游 profile 不一致",
            )

    def test_initial_height_and_default_pose_match_skill_factory(self):
        """出生高 / 默认姿必须等于**该技能自己的**机器人变体（没覆盖才回落基座）。"""
        base = _base_init_state()
        for entry in self.policies:
            skill = self._skill_of(entry)
            factory = _robot_factory(skill)
            pos = factory["pos"] or base["pos"]
            joint_pos = factory["joint_pos"] or base["joint_pos"]
            contract = entry.get("contract") or {}
            if pos:
                self.assertAlmostEqual(
                    float(pos[2]), float(contract.get("initial_base_height") or 0.0),
                    places=6, msg=f"{entry['id']}：initial_base_height 与上游 {skill}_robot_cfg 不一致",
                )
            mismatch = []
            for name in contract.get("action_joint_order") or []:
                want = _resolve_joint(joint_pos, name)
                got = (contract.get("default_joint_angles") or {}).get(name)
                if want is None or got is None:
                    continue
                if abs(float(want) - float(got)) > 1e-6:
                    mismatch.append(f"{name}: 契约 {got} vs 上游 {want}")
            self.assertEqual([], mismatch, f"{entry['id']} 默认姿与上游不一致：{mismatch}")

    def test_artifact_metadata_matches_contract(self):
        """**产物自证**：ONNX 自带元数据时，契约必须与它逐值一致（最硬的一手年代真值）。

        实测只有 `go2-handstand.onnx` 带元数据（其余 7 个的 `custom_metadata_map` 为空），
        它给出 `default_joint_pos` 12 值 / `action_scale` / `joint_names` / `command_names` /
        `observation_names` —— 这份元数据**确认了默认姿**（`0.1,0.8,-1.5,-0.1,0.8,-1.5,0.1,1.0,-1.5,
        -0.1,1.0,-1.5`，与我们从技能工厂取的值一致 ✓，即"逐技能工厂"这条路走对了）。

        **它 settle 不了增益**：`joint_stiffness` 全 1.0、`joint_damping` 全 −0.0 是导出占位
        （不是训练真值）⇒ 增益年代问题仍按 `test_gain_era_evidence` 的行为证据处理。
        没有元数据的产物跳过（不假装有）。
        """
        checked = 0
        try:
            import onnxruntime as ort
        except ImportError:          # 精简环境（无 onnxruntime）时跳过，不假装验过
            self.skipTest("无 onnxruntime")
        from backend.policy_artifacts import policy_relative_path

        robot_dir = SIM_CFG.parents[1]
        for entry in self.policies:
            rel_name = policy_relative_path(entry, robot_dir=robot_dir)
            rel = (robot_dir / rel_name) if rel_name else None
            if rel is None or not rel.is_file():
                continue
            meta = ort.InferenceSession(str(rel), providers=["CPUExecutionProvider"]).get_modelmeta()
            props = dict(meta.custom_metadata_map or {})
            if not props:
                continue
            contract = entry.get("contract") or {}
            if props.get("action_scale"):
                self.assertAlmostEqual(float(props["action_scale"]),
                                       float(contract.get("action_scale")), places=6,
                                       msg=f"{entry['id']} action_scale 与产物元数据不一致")
            if props.get("joint_names"):
                self.assertEqual([x for x in str(props["joint_names"]).split(",") if x],
                                 list(contract.get("action_joint_order") or []), entry["id"])
            if props.get("default_joint_pos"):
                want = [float(x) for x in str(props["default_joint_pos"]).split(",") if x]
                got = [float((contract.get("default_joint_angles") or {})[n])
                       for n in contract.get("action_joint_order") or []]
                self.assertEqual(want, got, f"{entry['id']} 默认姿与产物元数据不一致")
            checked += 1
        self.assertGreater(checked, 0, "一个带元数据的产物都没验到——元数据来源变了？")

    def test_gain_era_evidence(self):
        """7 条 lainlab 的执行器增益 = **基座谱系**（hip/thigh 20/1、calf 40/2），不是现 `src` 工厂的 20/0.5。

        **这是一条"年代错配"的显式登记**（不是疏忽，也不是"回退顺手改绿"）：

        * 现快照 `skills/shared/robot.py` 的技能工厂把执行器改成 `hip/thigh/calf 全部 20/0.5`；
          而 `assets/robots/unitree_go2/go2_constants.py` 的基座执行器是 hip/thigh 20/1、calf **40/2**。
        * 包内这批 ONNX 是 **playground 随包的旧产物**：`skills/hand_stand/mdp/observations.py`
          自己注明"the successful bundled Gym policy was trained **before** these legacy fields
          were deleted" ⇒ 训练配置早于现 `src` 快照的那次执行器改动。
        * **行为证据（本机实测，同一批策略两套增益各跑一遍）**：现工厂值 20/0.5 下
          `spring-jump` **fail 4/5**（转向模式稳态倾角 36.5°）、`handstand` 稳态倾角 **0°**（更差）；
          基座值 20/1+40/2 下 5 条行动族全 5/5、`handstand` 33.5°、`rear-stand` 90°（均入 `posture` 带）。
        * **真仲裁者**是 playground 侧训练/导出时的配置——它**不在本快照内**（开源仓只有推理 demo）。
          所以这里把"当前采用值 + 两套候选值 + 证据"一起钉住：以后若换仲裁者，必须连本测试一起改。
        """
        want_hip_thigh, want_calf = (20.0, 1.0), (40.0, 2.0)
        for entry in self.policies:
            control = (entry.get("contract") or {}).get("control") or {}
            stiff = control.get("stiffness") or {}
            damp = control.get("damping") or {}
            self.assertTrue(stiff and damp, f"{entry['id']} 没声明增益（torque 接口下=零力矩）")
            for name in (entry["contract"].get("action_joint_order") or []):
                want = want_calf if "calf" in name else want_hip_thigh
                self.assertEqual((stiff[name], damp[name]), (want[0], want[1]),
                                 f"{entry['id']}.{name}：增益 {stiff[name]}/{damp[name]} 偏离已登记的证据值 {want}")

    def test_stand_skills_declare_source_frame_scales(self):
        """两条姿态类技能的 `scales` 必须与上游帧构造一致（本轮修的就是这条）。

        **断言 + 溯源**（不解析那段代码：各技能帧构造形态不同，硬解易碎）：
        `skills/hand_stand/mdp/observations.py::_stand_actor_frame` 与
        `_stand_actor_frame(..., constant_prefix_dim=3)`（handstand）写明
        `ang_vel × 0.25` / `cmd[:2] × 2.0` / `cmd[2:3] × 0.25` / `joint_vel × 0.05`，
        姿态类技能由此复用同一帧。此前两条契约**根本没声明 scales** ⇒ 引擎回落 1.0 ⇒
        这几段差 4×/2×/20× ⇒ 策略 0.5 s 内崩（对拍抓不到：浏览器读同一份错契约）。
        """
        for pid in ("go2-lainlab-rear-stand", "go2-lainlab-handstand"):
            entry = next(e for e in self.policies if e["id"] == pid)
            scales = (entry.get("contract") or {}).get("scales") or {}
            self.assertAlmostEqual(0.25, float(scales.get("ang_vel", 0)), places=6, msg=pid)
            self.assertAlmostEqual(0.05, float(scales.get("dof_vel", 0)), places=6, msg=pid)
            self.assertEqual([2.0, 2.0, 0.25], [float(x) for x in (scales.get("command") or [])], pid)


    def test_declared_layout_spec_self_consistent(self):
        """声明了 `observation_layout` 的策略：**段宽之和 == obs_dim**、来源名在词汇表内。

        规格是"布局的唯一陈述"，所以它自己必须先自洽（宽度、来源名）——本测试抓的就是
        "规格写错一段"（实测第一版 handstand 规格漏了 `cmd` 段，被引擎的宽度断言当场拦下：
        "构建 45 vs 契约 obs_dim=48"）。至于规格**是否等价于手写实现**，由
        `tools/obs_crosscheck.py` 的逐维对拍守（本测试不重复跑物理）。
        """
        spec_mod = importlib.util.spec_from_file_location(
            "policy_acceptance_for_layout_test", ROOT / "adapters" / "mjlab" / "policy_acceptance.py"
        )
        engine = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(engine)
        declared = 0
        for entry in self.policies:
            contract = entry.get("contract") or {}
            layout = contract.get("observation_layout")
            if not layout:
                continue
            total = 0
            for seg in layout:
                source = seg.get("source")
                self.assertIn(source, engine.OBS_LAYOUT_SOURCES, entry["id"])
                # 定宽来源（与解释器同规则：`gravity/euler` 3 维、相位各 1 维）；
                # 其余按声明宽度、缺省 = 动作关节数。
                fixed = {"gravity": 3, "euler": 3, "phase_sin": 1, "phase_cos": 1}
                total += int(seg.get("width") or fixed.get(source)
                             or len(contract.get("action_joint_order") or []))
            self.assertEqual(contract.get("obs_dim"), total,
                             f"{entry['id']}：声明式布局段宽之和 {total} ≠ obs_dim {contract.get('obs_dim')}")
            declared += 1
        self.assertGreaterEqual(declared, 7, "lainlab 七条都应声明 observation_layout")


if __name__ == "__main__":
    unittest.main()
