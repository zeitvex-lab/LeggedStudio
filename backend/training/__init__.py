"""Training API 子模块包。

拆分自 backend/training_api.py（原 god file，~960 行），按「创建/监控/产物/
健康/schema」职责划分，供 backend/training_api 聚合。各子模块 router 已自带
``/api/training`` 前缀，聚合后路径保持不变。
"""
