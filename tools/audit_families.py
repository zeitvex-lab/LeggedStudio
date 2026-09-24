"""族架构校验：把「同族机型可复用同一套技能训练」从口号变成可复跑的判据。

## 为什么需要它

用户对训练的口径是**通用架构**：只要是同架构（四足 / 轮足）的机器人，
各种技能训练（速度跟踪 / 越障 / 动作模仿 / 特技）都应该能复用。
"能复用"此前只存在于文档叙述与人工记忆里——本工具把它钉成数据 + 门禁：

| 检查 | 判据 | 抓什么 |
|---|---|---|
| 清单权威 | `registry/families/index.json` 列出的族 == 目录里的族文件 | 族文件放进去了但没登记（静默改契约） |
| 成员一致 | 声明成员 == 由契约 `morphology.id` **派生**的成员 | 新增机型漏登记 / 成员形态改名 / 契约被换掉 |
| 族约定 | 每台成员：腿数、locomotion_type、关节数 = 腿数 × 角色数、`leg_pattern` 能按别名映射到族角色、`control_hz` 同族 | 族内出现"其实不同构"的机型（通用性前提被破坏） |
| 技能覆盖 | 每个 profile 的 `task_name` **有且只有一个**技能声明它；反向：每个技能的声明覆盖 == 实测有档案的成员 | 游离任务（没人认领的新技能）+ 声明与事实漂移 |
| 缺口留痕 | 非 `generic` 技能必须写明 `gap`，且声明任务必须真有档案在用；`generic` 技能必须覆盖全族 | 缺口被悄悄"忘记"、通用性被高估，或"声称有能力、实际没有" |
| Kit 委派 | ① 每台成员的训练源码必须引用本族 Kit（`<family_id>_kit`）；② 族 Kit 里**不得 import** 机型包（`assets.robots` / `local_tasks`） | 成员自带一套框架副本（名义复用）；或 Kit 被写成某机型的专属库（方向搞反） |

**通用技能的 task_names 允许是超集**（`stairs` / `trot` 这类走通用任务路径，不依赖某台机型的档案）；
非通用技能反过来必须"声明 == 实测"，这条不对称是刻意的。

**不做**：不改任何包与档案，只读。身份/规格的真值仍在 `contract.json`；
本工具只核对"声明 vs 事实"，不复制任何数值。
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES_DIR = ROOT / "registry" / "families"
ROBOTS_DIR = ROOT / "assets" / "robots"
REQUIRED_SKILLS = ("velocity", "traversal", "imitation", "stunt")


def _load(path: Path) -> dict:
    # 编码口径跟仓库守卫 `backend/test_jsonio_single_source.py` 一致：读 JSON 必须吃 BOM
    # （`utf-8-sig` 同时吃带 BOM 与不带 BOM 的文件）。
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _contract(robots_dir: Path, robot_id: str) -> dict | None:
    path = robots_dir / robot_id / "contract.json"
    return _load(path) if path.exists() else None


def _profiles(robots_dir: Path, robot_id: str) -> list[dict]:
    found = []
    for raw in sorted(glob.glob(str(robots_dir / robot_id / "training" / "profiles" / "*.json"))):
        found.append(_load(Path(raw)))
    return found


def _derived_members(robots_dir: Path, morphology_ids: list[str], problems: list[str]) -> list[str]:
    """成员不硬编码：凡契约 morphology.id 落在本族形态集合内的机型，就是本族成员。"""
    members = []
    for contract_path in sorted(glob.glob(str(robots_dir / "*/contract.json"))):
        data = _load(Path(contract_path))
        if (data.get("morphology") or {}).get("id") in morphology_ids:
            members.append(data.get("robot_id") or Path(contract_path).parent.name)
    if not members:
        problems.append(f"形态 {morphology_ids} 没有任何机型契约 —— 族声明已与事实脱节")
    return members


def _role_resolution(pattern: list[str], aliases: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """把某机型的 leg_pattern 逐位映射到族角色；返回（角色序列, 未识别名）。"""
    resolved, unknown = [], []
    for name in pattern:
        hit = next((role for role, names in aliases.items() if name == role or name in names), None)
        if hit is None:
            unknown.append(name)
        else:
            resolved.append(hit)
    return resolved, unknown


def _check_member(family: dict, robots_dir: Path, robot_id: str, problems: list[str]) -> None:
    contract = _contract(robots_dir, robot_id)
    if contract is None:
        problems.append(f"{family['family_id']}/{robot_id}: 声明为成员，但 assets/robots/{robot_id}/contract.json 不存在")
        return
    morphology = contract.get("morphology") or {}
    control = contract.get("control") or {}
    joint_order = (contract.get("action") or {}).get("joint_order") or []
    roles = family["joint_roles"]
    where = f"{family['family_id']}/{robot_id}"

    if morphology.get("id") not in family["morphology_ids"]:
        problems.append(f"{where}: 形态 {morphology.get('id')} 不在族形态集合 {family['morphology_ids']}")
    if contract.get("locomotion_type") != family["locomotion_type"]:
        problems.append(f"{where}: locomotion_type={contract.get('locomotion_type')} 与族约定 {family['locomotion_type']} 不符")
    if morphology.get("legs") != family["legs"]:
        problems.append(f"{where}: 腿数 {morphology.get('legs')} 与族约定 {family['legs']} 不符")
    expected_joints = family["legs"] * len(roles)
    if len(joint_order) != expected_joints:
        problems.append(f"{where}: 关节数 {len(joint_order)} 与族约定 {expected_joints}（{family['legs']} 腿 × {len(roles)} 角色）不符")
    pattern = morphology.get("leg_pattern") or []
    if len(pattern) != len(roles):
        problems.append(f"{where}: leg_pattern 长度 {len(pattern)} 与族角色数 {len(roles)} 不符")
    else:
        resolved, unknown = _role_resolution(pattern, family["role_aliases"])
        if unknown:
            problems.append(f"{where}: leg_pattern 里的 {unknown} 无法映射到族角色 {roles} —— 新命名要在族声明的 role_aliases 里登记")
        elif resolved != roles:
            problems.append(f"{where}: leg_pattern 解析为 {resolved}，与族角色顺序 {roles} 不一致（顺序即角色语义）")
    if control.get("control_hz") != family["control_hz"]:
        problems.append(f"{where}: control_hz={control.get('control_hz')} 与族约定 {family['control_hz']} 不符（族内控制率必须同口径）")


def _actor_skeleton(robots_dir: Path, robot_id: str) -> list[str] | None:
    """该机型 v3 契约里的 actor 观测项序列（顺序即布局）。

    直接读声明数据，不走契约加载器：本工具核对的是"声明 vs 事实"，schema 校验是别处的
    职责（加载器要求整份契约齐备，而这里只需要 observation.components 这一段）。
    """
    path = robots_dir / robot_id / "contract.json"
    if not path.exists():
        return None
    try:
        components = ((_load(path).get("observation") or {}).get("components")) or []
    except json.JSONDecodeError:
        return None
    names = [str(item.get("name")) for item in components
             if isinstance(item, dict) and item.get("role", "actor") == "actor" and item.get("name")]
    return names or None


def _kit_name(family_id: str) -> str:
    """族 → 本族 Kit 模块名（`quadruped` → `quadruped_kit`）。不写进族声明：由族名派生，避免第二处真值。"""
    return f"{family_id}_kit"


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _check_kit_delegation(family: dict, robots_dir: Path, kits_dir: Path, members: list[str], problems: list[str]) -> None:
    """两条方向相反的不变量（2026-09-24 手工核对后固化为门禁）：

    1. **成员 → 族 Kit**：每台机型的训练源码至少要引用本族 Kit 一次（否则它自带一套框架副本，
       "同族复用"就只是名义上的）；
    2. **族 Kit → 不得反向依赖机型包**：Kit 里出现 `import` 机型包（`assets.robots` / `local_tasks`）
       就是方向搞反了 —— 那会让 Kit 变成"某机型的专属库"，别的成员再也复不了。

    注意：只查 **import 语句**；注释/docstring 里提来源路径是合法且必要的（出处说明）。
    """
    kit = _kit_name(str(family["family_id"]))
    kit_root = kits_dir / kit
    if not kit_root.exists():
        problems.append(f"{family['family_id']}: 本族 Kit {kit_root} 不存在")
        return
    for robot_id in members:
        source_root = robots_dir / robot_id / "training" / "source"
        if not source_root.exists():
            continue
        hits = [p for p in _python_files(source_root) if kit in p.read_text(encoding="utf-8", errors="ignore")]
        if not hits:
            problems.append(
                f"{family['family_id']}/{robot_id}: 训练源码里找不到对本族 Kit `{kit}` 的任何引用"
                f"（要么自带了一套框架副本，要么入口没接 Kit）")
    import_re = re.compile(r"^\s*(?:from|import)\s+[^\n]*?(assets\.robots|local_tasks)")
    for path in _python_files(kit_root):
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if import_re.search(line):
                problems.append(
                    f"{kit}/{path.relative_to(kit_root)}:{lineno}: Kit 反向 import 了机型包代码：{line.strip()[:80]}"
                    f"（Kit 必须与机型无关；机型差异走契约或调用方传入）")
                break


def _check_observation_skeleton(family: dict, robots_dir: Path, members: list[str], problems: list[str]) -> None:
    """族级观测骨架：actor 项序列按族声明；偏差必须显式登记（登记了又不符合也不行）。

    为什么不做"自动归一"：项序就是策略输入布局，改宽/重排会让存量策略失效，
    属需单独裁决的迁移。本检查只保证**分歧可见**——不登记就判红，登记了就不再是暗坑。
    """
    skeleton = family.get("observation_skeleton")
    where = family["family_id"]
    if not skeleton:
        problems.append(f"{where}: 缺 observation_skeleton —— 同族观测骨架没有真值，分歧只能靠人记")
        return
    expected = list(skeleton.get("actor") or [])
    if not expected:
        problems.append(f"{where}: observation_skeleton.actor 为空")
        return
    overlap = sorted(set(expected) & set(skeleton.get("critic_only") or []))
    if overlap:
        problems.append(f"{where}: 观测骨架自相矛盾——{overlap} 同时出现在 actor 与 critic_only")

    deviations = dict(skeleton.get("deviations") or {})
    for robot_id in deviations:
        if robot_id not in members:
            problems.append(f"{where}: 观测偏差登记了非本族成员 {robot_id}")
    for robot_id in members:
        observed = _actor_skeleton(robots_dir, robot_id)
        if observed is None:
            continue
        declared = deviations.get(robot_id)
        if observed == expected:
            if declared:
                problems.append(f"{where}/{robot_id}: 已与族骨架一致，但偏差登记还在（登记要跟着事实走，请删除）")
            continue
        if not declared:
            problems.append(
                f"{where}/{robot_id}: actor 观测骨架与族约定不一致且未登记偏差\n"
                f"    族骨架: {expected}\n"
                f"    实测  : {observed}"
            )
        elif not str(declared).strip():
            problems.append(f"{where}/{robot_id}: 偏差登记为空说明")


def _check_skill_terrains(family: dict, skill: dict, problems: list[str]) -> None:
    """技能的**地形轴**（用户口径：越障看训练地形，不看技能叫什么名字）。

    技能可以声明 `terrain_profiles`（该技能覆盖哪些地形档，id 见 `registry/terrains`）。判据双向：
    * 档位 id 必须真实存在（未登记即判红）；
    * 本族**已就绪**的档不许再挂在 `terrain_pending`（登记要跟着事实走）；
    * 本族**未就绪**的档必须显式列进 `terrain_pending`（缺口诚实留痕，同 gap 的精神）。
    """
    where = family["family_id"]
    skill_id = skill.get("skill_id")
    terrains = skill.get("terrain_profiles")
    if terrains is None:
        return
    from adapters.mjlab import terrain_profiles as _terrain_profiles

    pending = [str(x) for x in skill.get("terrain_pending") or []]
    for profile_id in [str(x) for x in terrains]:
        try:
            status = _terrain_profiles.availability(profile_id, where)
        except _terrain_profiles.TerrainProfileError as exc:
            problems.append(f"{where}/{skill_id}: 地形档 {profile_id!r} 不在 registry/terrains（{exc}）")
            continue
        if status == "ready" and profile_id in pending:
            problems.append(f"{where}/{skill_id}: 地形档 {profile_id} 在本族已就绪，却仍挂在 terrain_pending（登记没跟着事实走）")
        if status == "missing" and profile_id not in pending:
            problems.append(f"{where}/{skill_id}: 地形档 {profile_id} 在本族未就绪，必须列进 terrain_pending（缺口要留痕）")
    for profile_id in pending:
        if profile_id not in terrains:
            problems.append(f"{where}/{skill_id}: terrain_pending 里的 {profile_id} 不在 terrain_profiles 清单内")


def _check_skills(family: dict, robots_dir: Path, members: list[str], problems: list[str]) -> dict[str, set[str]]:
    skills = family.get("skills") or []
    where = family["family_id"]
    by_skill_id = {skill.get("skill_id"): skill for skill in skills}

    for required in REQUIRED_SKILLS:
        if required not in by_skill_id:
            problems.append(f"{where}: 缺少必备技能类 {required}（四类技能：{'/'.join(REQUIRED_SKILLS)}）")

    claimed: dict[str, str] = {}
    for skill in skills:
        for task_name in skill.get("task_names") or []:
            if task_name in claimed:
                problems.append(f"{where}: 任务 {task_name} 被技能 {claimed[task_name]} 与 {skill['skill_id']} 同时声明（归类必须唯一）")
            claimed[task_name] = skill["skill_id"]

    observed: dict[str, set[str]] = {skill.get("skill_id"): set() for skill in skills}
    used_tasks: dict[str, set[str]] = {skill.get("skill_id"): set() for skill in skills}
    for robot_id in members:
        for profile in _profiles(robots_dir, robot_id):
            task_name = str(profile.get("task_name"))
            profile_id = profile.get("profile_id") or "?"
            skill_id = claimed.get(task_name)
            if skill_id is None:
                problems.append(f"{where}/{robot_id}: 档案 {profile_id} 的 task_name={task_name} 没有任何技能声明它（游离任务）")
                continue
            observed.setdefault(skill_id, set()).add(robot_id)
            used_tasks.setdefault(skill_id, set()).add(task_name)

    for skill in skills:
        skill_id = skill.get("skill_id")
        declared = set(members) if skill.get("status") == "generic" else set(skill.get("members_with_recipe") or [])
        seen = observed.get(skill_id, set())
        _check_skill_terrains(family, skill, problems)
        if skill.get("status") == "generic":
            if not seen:
                problems.append(f"{where}/{skill_id}: 标为族级通用，但没有一台成员有对应档案")
            missing = set(members) - seen
            if missing:
                problems.append(f"{where}/{skill_id}: 标为族级通用，但这些成员没有对应档案：{sorted(missing)}")
        else:
            if declared != seen:
                problems.append(f"{where}/{skill_id}: 声明可训成员 {sorted(declared)} 与实测有档案的成员 {sorted(seen)} 不一致")
            if not skill.get("gap"):
                problems.append(f"{where}/{skill_id}: 非族级通用（status={skill.get('status')}）却没有写 gap —— 缺口必须留痕")
            idle = set(skill.get("task_names") or []) - used_tasks.get(skill_id, set())
            if idle:
                problems.append(f"{where}/{skill_id}: 声明了这些任务但没有任何档案在用：{sorted(idle)}")
        if declared - set(members):
            problems.append(f"{where}/{skill_id}: 声明成员 {sorted(declared - set(members))} 不在本族成员里")
    return observed


def audit(families_dir: Path = FAMILIES_DIR, robots_dir: Path = ROBOTS_DIR,
          kits_dir: Path | None = None) -> dict:
    """只读核验：返回 {ok, problems, matrix, families}。"""
    if kits_dir is None:
        kits_dir = ROOT / "adapters" / "mjlab" / "kits"
    problems: list[str] = []
    index_path = families_dir / "index.json"
    if not index_path.exists():
        return {"ok": False, "problems": [f"缺族清单：{index_path}"], "matrix": [], "families": 0}

    index = _load(index_path)
    entries = index.get("families") or []
    registered = [entry.get("path") for entry in entries]
    on_disk = sorted(p.name for p in families_dir.glob("*.json") if p.name != "index.json")
    for name in on_disk:
        if name not in registered:
            problems.append(f"族文件 {name} 存在于 registry/families/ 但未在 index.json 登记")
    for name in registered:
        if name not in on_disk:
            problems.append(f"index.json 登记了 {name}，但文件不存在")

    matrix: list[tuple[str, str, int, int]] = []
    for entry in entries:
        path = families_dir / str(entry.get("path"))
        if not path.exists():
            continue
        family = _load(path)
        family_id = family.get("family_id")
        if family_id != entry.get("family_id"):
            problems.append(f"{path.name}: family_id={family_id} 与清单登记 {entry.get('family_id')} 不一致")
        members = _derived_members(robots_dir, family.get("morphology_ids") or [], problems)
        declared_members = family.get("members") or []
        if sorted(members) != sorted(declared_members):
            problems.append(
                f"{family_id}: 声明成员 {sorted(declared_members)} 与契约派生成员 {sorted(members)} 不一致"
                f"（新增/移除机型时要同步族声明）")
        for robot_id in declared_members:
            _check_member(family, robots_dir, robot_id, problems)
        _check_kit_delegation(family, robots_dir, kits_dir, members, problems)
        _check_observation_skeleton(family, robots_dir, members, problems)
        observed = _check_skills(family, robots_dir, members, problems)
        for skill in family.get("skills") or []:
            matrix.append((family_id, skill.get("skill_id"), len(observed.get(skill.get("skill_id"), set())), len(members)))

    return {"ok": not problems, "problems": problems, "matrix": matrix, "families": len(entries)}


def main() -> int:
    parser = argparse.ArgumentParser(description="族架构校验（声明 vs 事实）")
    parser.add_argument("--quiet", action="store_true", help="只打印结论与问题")
    args = parser.parse_args()

    report = audit()
    if not args.quiet:
        print("[families] 技能覆盖（族 × 技能 → 有档案的成员数 / 族规模）")
        for family_id, skill_id, seen, total in report["matrix"]:
            flag = "✓" if seen == total else ("·" if seen else "✗")
            print(f"  {flag} {family_id:10s} {skill_id:10s} {seen}/{total}")
    if report["problems"]:
        print(f"\n[families] {len(report['problems'])} 个问题：")
        for item in report["problems"]:
            print(f"  - {item}")
        return 1
    print(f"\n[families] 全部通过：{report['families']} 个族、{len(report['matrix'])} 格技能矩阵")
    return 0


if __name__ == "__main__":
    sys.exit(main())
