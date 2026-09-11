# IK 真机控制探索

该目录保存强化学习部署前的逆运动学真机控制代码。

- `sim2real_control_api.py`：真机控制接口
- `trajectory_interpolator.py`：关节/姿态轨迹插值
- `sim_to_real_deploy_beifen.py`：早期部署脚本备份

文件名中的 `beifen` 来自原始资料。为保持早期版本可追溯性，本次归档不修改源码和文件名。

## 可移植性说明

- `trajectory_interpolator.py` 的图片输出仍指向原开发机绝对路径。
- `sim_to_real_deploy_beifen.py` 是历史备份脚本，包含旧工作区 `sys.path`、旧根目录和 `/dev/can*` 参数，不能作为新环境的直接部署入口。
- 这些路径被保留用于说明早期来源；公开复用前应改为命令行参数或相对路径，并重新验证电机映射和安全边界。
