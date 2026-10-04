"""族级 AMP 算法实现——**已上移**算法插件层（薄 re-export，入口符号不变）。

上移理由（2026-10-04）：AMP 源口径实现归算法插件层（adapters/mjlab/algorithms/amp），
跨族可用；本模块保留 import 兼容（go2 薄委托/go1_amp 消费者不动）。
"""

from adapters.mjlab.algorithms.amp.source_amp import (  # noqa: F401
    AmpPpoMixin,
    AmpPPO,
)
