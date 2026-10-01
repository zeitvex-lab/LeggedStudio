"""任务档组装端点：列目录的诚实可用性 + 组装载荷的可跑性（registry/tasks 真值表）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api_complete import app

client = TestClient(app)


def test_list_profiles_reports_browser_availability_honestly() -> None:
    resp = client.get("/api/task-profiles")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    by_id = {p["task_id"]: p for p in payload["profiles"]}
    # 注册表里声明的每档都在列（阻断不隐藏——如实列出原因）
    assert {"goal_nav_warehouse", "patrol_warehouse_full", "follow_line", "traversal_obstacle_course"} <= set(by_id)
    # planner+warehouse 两档浏览器可跑
    assert by_id["goal_nav_warehouse"]["browser_ok"] is True
    assert by_id["goal_nav_warehouse"]["browser_blockers"] == []
    # follow_line 声明了 browser 但 command_source=script 没有浏览器执行器 ⇒ 阻断要说清
    assert by_id["follow_line"]["browser_ok"] is False
    assert any("script" in b for b in by_id["follow_line"]["browser_blockers"])
    # traversal 只声明 headless/cli ⇒ 浏览器阻断
    assert by_id["traversal_obstacle_course"]["browser_ok"] is False
    assert any("availability" in b for b in by_id["traversal_obstacle_course"]["browser_blockers"])


def test_assemble_goal_navigation_is_runnable_scenario() -> None:
    resp = client.get("/api/task-profiles/goal_nav_warehouse/assemble")
    assert resp.status_code == 200
    data = resp.json()
    assert data["blockers"] == []
    scenario = data["scenario"]
    assert scenario["scenario_id"] == "goal_nav_warehouse"
    assert scenario["command_source"] == "planner"
    assert scenario["mode"] == "navigation"
    # goal 模式 = 首末航点（起点 + 目标），planner 才有 ≥2 航点可用
    assert len(scenario["waypoints"]) == 2
    assert scenario["waypoints"][0] == {"x": 0.0, "y": 0.0}
    assert scenario["waypoints"][-1] == {"x": 6.0, "y": 0.0}
    # 感知绑定来自插件实例化（odom-waypoint-nav：odom/imu，无阻断时 readiness 存在）
    assert data["readiness"] is not None
    assert data["cli_criteria"].startswith("python tools/run_task_profile.py")


def test_assemble_patrol_takes_all_default_waypoints() -> None:
    resp = client.get("/api/task-profiles/patrol_warehouse_full/assemble")
    assert resp.status_code == 200
    data = resp.json()
    assert data["blockers"] == []
    assert len(data["scenario"]["waypoints"]) == 4


def test_assemble_blocked_profiles_still_return_payload_with_reasons() -> None:
    # 阻断档**不报错**——返回载荷 + 阻断清单，前端据此禁用应用按钮
    for task_id in ("follow_line", "traversal_obstacle_course"):
        resp = client.get(f"/api/task-profiles/{task_id}/assemble")
        assert resp.status_code == 200
        data = resp.json()
        assert data["blockers"], f"{task_id} 应有阻断原因"
        assert data["cli_criteria"], f"{task_id} 应给 headless/人工判据出口"


def test_assemble_unknown_profile_fails_closed_with_available_ids() -> None:
    resp = client.get("/api/task-profiles/definitely-not-a-task/assemble")
    assert resp.status_code == 404
    assert "goal_nav_warehouse" in resp.json()["detail"]
