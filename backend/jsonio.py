"""JSON 读写：**实现住在 ``contracts/jsonio.py``**（此处只做 re-export）。

为什么不把实现放这里：它要同时被 ``backend/``、``tools/``、``contracts/`` 三处复用 ——
``contracts`` 是最底层且零第三方依赖，放那里才不会出现"底层反向依赖控制面"。
保留本模块是为了既有 ``from backend.jsonio import ...`` 的 import 路径不用改。
"""

from contracts.jsonio import JSON_ENCODING, dumps, load_json, read_json, write_json  # noqa: F401

__all__ = ["JSON_ENCODING", "dumps", "load_json", "read_json", "write_json"]
