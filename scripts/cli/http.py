"""CLI 共享 HTTP 助手（自 scripts/legged_studio_cli.py 拆分，2026-10-12；函数体零改动）。

与 Web 工作台同一契约的 HTTP 封装 + 错误中文化提示。
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen



def _http_detail_hint(detail: str) -> str | None:
    """从错误体里提取人类可读原因（FastAPI 的 detail 可能是字符串或 dict）。"""

    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    inner = parsed.get("detail")
    if isinstance(inner, str):
        return inner
    if isinstance(inner, dict):
        for key in ("message", "reason"):
            value = inner.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _request(
    base_url: str,
    method: str,
    route: str,
    payload: object | None = None,
    *,
    headers: dict[str, str] | None = None,
    unreachable_hint: str | None = None,
    friendly_http: bool = False,
) -> object:
    """对控制面发一次 HTTP 请求并解析 JSON 响应。

    关键字参数只被训练在线命令（I1 第二批）使用，默认关闭时行为与既有
    10 个 HTTP 门面命令完全一致：

    * ``headers``          —— 追加请求头（如 Idempotency-Key）；
    * ``unreachable_hint`` —— 连接失败时的中文可操作提示模板（{base}/{reason} 占位）；
    * ``friendly_http``    —— HTTP 错误体里提取 message/reason 给可读行（原始体仍保留）。
    """

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    all_headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    request = Request(f"{base_url.rstrip('/')}{route}", data=body, method=method, headers=all_headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if friendly_http:
            hint = _http_detail_hint(detail)
            if hint:
                raise SystemExit(f"HTTP {exc.code} 请求被拒：{hint}\n{detail}") from exc
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if unreachable_hint:
            raise SystemExit(unreachable_hint.format(base=base_url, reason=reason)) from exc
        raise SystemExit(f"无法连接控制平面 {base_url}: {reason}") from exc


def _json_file(path: str) -> dict:
    """读 JSON 对象（编码口径见 contracts/jsonio：吃 BOM）；非对象即报错。"""

    from contracts.jsonio import load_json

    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"not a JSON object: {path}")
    return value


# --------------------------------------------------------------------------------------
# 离线命令（I1 第一批）：不连控制面，直接读仓库数据；逻辑一律复用 backend/，这里只做输出
# --------------------------------------------------------------------------------------
