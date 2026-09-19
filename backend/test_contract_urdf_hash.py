"""v2 ``urdf.hash`` 全仓不变量 + **一个工件只有一个哈希**（2026-09-16 收口）。

## 这组测试守的是什么

``contracts/validator.py`` 在训练创建链上校验 ``urdf.hash``（``/api/training/create``
→ ``Invalid contract: URDF hash mismatch``）。2026-09-16 跑 L7 最后一台 ``zex-w`` 时
实测：``zex-w`` 与 ``unitree_go2w`` 两包**提交在仓库里**的 ``urdf.hash`` 与磁盘
``model/robot.xml`` 对不上（工作树与 HEAD 逐字节一致 ⇒ 不是检出差异），于是产品路径
在**任何机器上**都 400。B27 那次修复没有测试守护，因此"修好过"这件事无法被验证。

两处根因，本文件各钉一条：

1. **数据失同步**（两包）→ 重签；且用**不变量**守住：14 包任一包只要声明了非空
   ``urdf.hash``，就必须等于磁盘实测值。空串是设计性跳过（validator 明写
   ``if contract.urdf.hash``），不算缺口，但**已声明的包清单钉死在允许集里** ——
   新声明一个哈希是有意动作，必须连同本测试一起改。
2. **两套哈希口径**：``contracts/validator._compute_file_hash`` 原先对**原始字节**
   求 SHA-256，而 ``backend/pack_catalog._content_sha256``（与
   ``tools/generate_packs.py::_sha256``）是 **CRLF → LF 归一** —— 同一份资产在
   Windows 与 CI 上会得到两个哈希（B27 已登记的存量风险）。本文件把"两个模块算出
   同一个数"钉成断言，避免任何一侧被单独改回去。

判据只用**validator 自己的实现**（``_compute_file_hash``）去算，测试里不另写一份
算法 —— 否则"测试通过"只证明测试自洽，不证明产品路径通过。

风格：纯 unittest（CI 的 ``unittest discover`` 与本地 ``python -m pytest`` 双口径可跑）。
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pack_catalog import _content_sha256  # noqa: E402
from contracts.validator import RobotContractValidator  # noqa: E402

ROBOTS = ROOT / "assets" / "robots"

#: 当前**声明了非空** ``urdf.hash`` 的包（2026-09-16 重签后实测）。
#: 其余 12 包是空串 = validator 设计性跳过（不算缺口）。新声明一个哈希意味着
#: "这份模型从此被锁住"，是有意动作：签完请把它加进本集合。
DECLARED_HASH_ROBOTS = frozenset({"unitree_go2w", "zex-w"})


def _builtin_robots() -> list[str]:
    """有 v2+v3 双契约的内置包清单（与 B32 同口径）。"""
    return sorted(
        d.name for d in ROBOTS.iterdir()
        if d.is_dir() and (d / "contract_legacy_v2.json").exists() and (d / "contract.json").exists()
    )


def _declared_hash(robot: str) -> str:
    payload = json.loads((ROBOTS / robot / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
    return str(((payload.get("urdf") or {}).get("hash")) or "")


def _asset_path(robot: str) -> Path:
    payload = json.loads((ROBOTS / robot / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
    return ROOT / str((payload.get("urdf") or {}).get("path"))


class UrdfHashSyncInvariantTest(unittest.TestCase):
    """全仓不变量：声明了 ``urdf.hash`` 的包必须与磁盘实测一致。"""

    def test_declared_hashes_match_disk(self):
        """逐包对账；不一致时报出 {包: (契约值, 实测值)} 与重签对象。"""
        mismatch: dict[str, tuple[str, str]] = {}
        for robot in _builtin_robots():
            declared = _declared_hash(robot)
            if not declared:
                continue  # 空串 = 设计性跳过（validator 的行为，不是缺口）
            actual = RobotContractValidator._compute_file_hash(_asset_path(robot))
            if declared != actual:
                mismatch[robot] = (declared[:12], actual[:12])
        self.assertEqual(
            {}, mismatch,
            "这些包的 v2 urdf.hash 与磁盘 model 文件对不上 {包: (契约前 12 位, 实测前 12 位)} —— "
            "产品路径会在 /api/training/create 直接 400。"
            "按磁盘实测重签（口径见 validator._compute_file_hash：CRLF → LF 归一）",
        )

    def test_declared_hash_allowlist(self):
        """已声明的包集合钉死：新锁一份模型是有意动作，须连同本测试一起改。"""
        declared = {robot for robot in _builtin_robots() if _declared_hash(robot)}
        self.assertEqual(
            set(DECLARED_HASH_ROBOTS), declared,
            "urdf.hash 的声明集合变了——若为有意动作请更新 DECLARED_HASH_ROBOTS",
        )

    def test_every_builtin_package_has_readable_urdf_path(self):
        """空串也不许指向不存在的文件（"跳过哈希"不等于"跳过存在性"）。"""
        missing = [
            robot for robot in _builtin_robots() if not _asset_path(robot).is_file()
        ]
        self.assertEqual([], missing, "这些包的 urdf.path 指向的文件不存在")


class SingleHashingRuleTest(unittest.TestCase):
    """一个工件只有一个哈希：契约校验器与 Pack 对账必须是同一口径。"""

    def test_validator_and_pack_catalog_agree(self):
        """同一份字节，两个模块必须得到同一个数（B27 登记的存量不一致在此收口）。"""
        for payload in (b"<mujoco/>\n", b"<mujoco/>\r\n", b"a\r\nb\r\nc", b"plain"):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "robot.xml"
                path.write_bytes(payload)
                self.assertEqual(
                    _content_sha256(payload),
                    RobotContractValidator._compute_file_hash(path),
                    f"两个模块对同一字节串算出不同哈希：{payload!r}",
                )

    def test_hash_is_line_ending_independent(self):
        """CRLF 与 LF 同一哈希（跨平台检出不再漂移）。"""
        with tempfile.TemporaryDirectory() as tmp:
            lf, crlf = Path(tmp) / "lf.xml", Path(tmp) / "crlf.xml"
            lf.write_bytes(b"<mujoco>\n  <worldbody/>\n</mujoco>\n")
            crlf.write_bytes(b"<mujoco>\r\n  <worldbody/>\r\n</mujoco>\r\n")
            self.assertEqual(
                RobotContractValidator._compute_file_hash(lf),
                RobotContractValidator._compute_file_hash(crlf),
            )

    def test_hash_is_still_content_sensitive(self):
        """归一化只动行尾：改内容哈希必须变（否则锁不住模型漂移）。"""
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.xml", Path(tmp) / "b.xml"
            a.write_bytes(b"<mujoco><option timestep='0.005'/></mujoco>")
            b.write_bytes(b"<mujoco><option timestep='0.002'/></mujoco>")
            self.assertNotEqual(
                RobotContractValidator._compute_file_hash(a),
                RobotContractValidator._compute_file_hash(b),
            )

    def test_whole_file_read_avoids_chunk_boundary_leak(self):
        """``\\r\\n`` 跨 4096 字节边界也必须归一（分块读的老实现会漏这一处）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.xml"
            # 让 CRLF 恰好落在 4096 边界上：4095 字节前缀 + "\r\n" + 尾巴
            path.write_bytes(b"x" * 4095 + b"\r\n" + b"y\r\nz\n")
            expected = hashlib.sha256(
                b"x" * 4095 + b"\n" + b"y\nz\n"
            ).hexdigest()
            self.assertEqual(expected, RobotContractValidator._compute_file_hash(path))


if __name__ == "__main__":
    unittest.main()
