"""Map metadata shared by navigation and interactive simulation APIs.

This module intentionally has no NumPy or MuJoCo imports. Native MJLab
navigation can validate map requests even when interactive simulator
dependencies are not installed in the control-plane environment.
"""

from __future__ import annotations

from typing import Any


MAPS: dict[str, dict[str, Any]] = {
    "flat": {
        "id": "flat",
        "label": "Flat / \u57fa\u7840\u9065\u63a7",
        "kind": "flat",
        "mode": "basic",
        "description": "\u5e73\u9762\u73af\u5883\uff0c\u7528\u4e8e\u5173\u8282\u548c\u901f\u5ea6\u6307\u4ee4\u7684\u5feb\u901f\u68c0\u67e5",
        "bounds": [-5.0, 5.0, -5.0, 5.0],
    },
    "warehouse": {
        "id": "warehouse",
        "label": "Warehouse / \u5bfc\u822a",
        "kind": "grid",
        "mode": "navigation",
        "description": "\u5e26\u56fa\u5b9a\u969c\u788d\u7269\u7684\u4e8c\u7ef4\u8def\u7ebf\u573a\u666f\uff0c\u9002\u5408 waypoint \u4efb\u52a1",
        "bounds": [-2.0, 8.0, -4.0, 4.0],
        "obstacles": [[2.0, -1.2, 0.6, 2.4], [4.5, 0.8, 0.8, 2.0]],
        "default_waypoints": [[0.0, 0.0], [1.5, 2.2], [3.2, 2.2], [6.0, 0.0]],
    },
    "rough": {
        "id": "rough",
        "label": "Rough / \u590d\u6742\u5730\u5f62",
        "kind": "terrain",
        "mode": "navigation",
        "description": "\u7c97\u7cd9\u5730\u5f62\u4efb\u52a1\u5143\u6570\u636e\uff1bnative MJLab terrain adapter \u53ef\u63a5\u5165",
        "bounds": [-2.0, 8.0, -4.0, 4.0],
        "default_waypoints": [[0.0, 0.0], [2.0, 0.5], [4.0, -0.8], [6.0, 0.0]],
    },
    "stairs": {
        "id": "stairs",
        "label": "Stairs / \u7279\u5b9a\u4efb\u52a1",
        "kind": "terrain",
        "mode": "navigation",
        "description": "\u697c\u68af\u8def\u7ebf\u4efb\u52a1\u5143\u6570\u636e\uff0c\u901a\u8fc7 Scenario Contract \u7ed1\u5b9a\u5b9e\u9645\u5730\u5f62",
        "bounds": [-2.0, 8.0, -4.0, 4.0],
        "default_waypoints": [[0.0, 0.0], [2.0, 0.0], [4.0, 0.8], [6.0, 1.6]],
    },
}
