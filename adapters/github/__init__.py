"""GitHub 镜像（自动上传）适配器。

设计与 ``adapters/`` 下其他成员一致：**只用标准库**，不引入新依赖，
控制面/CI 都能直接 import；真正的 git 动作走 git CLI。

**刻意不在包 ``__init__`` 里 re-export** `mirror` 的符号：`mirror.py` 是有 `main()`
的可执行入口（`python -m adapters.github.mirror`），在包初始化时就 import 它，
会让 `-m` 触发 `RuntimeWarning: 'adapters.github.mirror' found in sys.modules ...`。
需要符号时直接 `from adapters.github.mirror import load_credentials`。
"""
