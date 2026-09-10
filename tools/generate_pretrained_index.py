# -*- coding: utf-8 -*-
"""A4：生成 pretrained_models/index.json。

数据源（数据驱动，无 per-robot 分支）：
  1. 内置策略：各包 simulation/config.json 的 policies + demo_policies
     （与 /api/health/demo-cards 同源）——这是索引的主体；
  2. 本地训练产物：pretrained_models/*/artifact.json（若存在，按 id 合并、
     指标优先）——scripts/generate_pretrained_models.py 训练出的模型。

产出字段与 /api/pretrained/* 的消费者对齐（dashboard quickDemo、首页 demo 卡）：
  id / name / robot / algorithm / success_rate / avg_reward / path / url / play_url
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.health_api import demo_cards  # noqa: E402


def main() -> None:
    cards = asyncio.run(demo_cards()).get("cards", [])

    models: dict[str, dict] = {}
    for card in cards:
        # 复合 id 与 /api/pretrained/list 的 package-scan 回落路径同约定
        # （pretrained_api: f"{robot_id}--{id}"）。裸 policy id 会跨机型撞名
        # ——曾致 b2/b2w 的 robotlab-velocity-57 互相覆盖、b2w 静默消失。
        model_id = f"{card['robot_id']}--{card['id']}"
        models[model_id] = {
            "id": model_id,
            "name": str(card.get("label") or card["id"]),
            "robot": str(card.get("robot_id")),
            "family": card.get("family"),
            "algorithm": "PPO",
            # 内置策略不带训练指标：置 null，前端须判空（勿伪造成功率）
            "success_rate": None,
            "avg_reward": None,
            "path": str(card.get("url") or ""),
            "url": str(card.get("url") or ""),
            "play_url": str(card.get("play_url") or ""),
            "obs_dim": card.get("obs_dim"),
            "action_dim": card.get("action_dim"),
            "source": "builtin-package",
        }

    # 本地训练产物（可选）：指标真实存在才覆盖
    pretrained_dir = ROOT / "pretrained_models"
    for artifact_file in sorted(pretrained_dir.glob("*/artifact.json")):
        try:
            artifact = json.loads(artifact_file.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        model_id = str(artifact.get("artifact_id") or artifact_file.parent.name)
        models[model_id] = {
            "id": model_id,
            "name": str(artifact.get("task_name") or model_id),
            "robot": str(
                (artifact.get("robot_contract_snapshot") or {}).get("robot_id") or "unknown"
            ),
            "algorithm": str(artifact.get("algorithm") or "PPO"),
            "success_rate": (artifact.get("metrics") or {}).get("success_rate"),
            "avg_reward": (artifact.get("metrics") or {}).get("avg_reward"),
            "path": str(artifact_file.parent),
            "url": "",
            "play_url": "",
            "obs_dim": None,
            "action_dim": None,
            "source": "local-training",
        }

    ordered = [models[k] for k in sorted(models)]
    pretrained_dir.mkdir(parents=True, exist_ok=True)
    index_path = pretrained_dir / "index.json"
    index_path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    builtin = sum(1 for m in ordered if m["source"] == "builtin-package")
    print(f"index.json: {index_path}")
    print(f"  total={len(ordered)} (builtin={builtin}, local-training={len(ordered) - builtin})")
    robots = sorted({m["robot"] for m in ordered})
    print(f"  robots ({len(robots)}): {', '.join(robots)}")


if __name__ == "__main__":
    main()
