# legged_sim — 参考资源

> **来源**：`00_open/legged_sim/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：G1 仿真环境与场景
> **收录**：38 个文件 / 106 KB（其中推理策略/模型文件 0 个）
> **已省略**：9 个文件 / 70.8 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（7 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（13 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **地形与场景**（4 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **文档与其它**（14 个）：文档、说明、许可与零散脚本

## 目录构成

```text
LeggedLab/  （38 个文件）
    (直接文件)/
    .github/
    legged_lab/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 28 |
| `(无扩展名)` | 4 |
| `.yaml` | 3 |
| `.txt` | 2 |
| `.md` | 1 |

## 文件索引（项目内相对路径）

```text
LeggedLab/.flake8
LeggedLab/.github/LICENSE_HEADER.txt
LeggedLab/.gitignore
LeggedLab/.pre-commit-config.yaml
LeggedLab/LICENSE.txt
LeggedLab/README.md
LeggedLab/legged_lab/__init__.py
LeggedLab/legged_lab/assets/__init__.py
LeggedLab/legged_lab/assets/fftai/__init__.py
LeggedLab/legged_lab/assets/fftai/fftai.py
LeggedLab/legged_lab/assets/fftai/gr2/.asset_hash
LeggedLab/legged_lab/assets/fftai/gr2/config.yaml
LeggedLab/legged_lab/assets/unitree/__init__.py
LeggedLab/legged_lab/assets/unitree/g1/.asset_hash
LeggedLab/legged_lab/assets/unitree/g1/config.yaml
LeggedLab/legged_lab/assets/unitree/unitree.py
LeggedLab/legged_lab/envs/__init__.py
LeggedLab/legged_lab/envs/base/base_config.py
LeggedLab/legged_lab/envs/base/base_env.py
LeggedLab/legged_lab/envs/base/base_env_config.py
LeggedLab/legged_lab/envs/g1/g1_config.py
LeggedLab/legged_lab/envs/gr2/gr2_config.py
LeggedLab/legged_lab/envs/h1/h1_config.py
LeggedLab/legged_lab/mdp/__init__.py
LeggedLab/legged_lab/mdp/rewards.py
LeggedLab/legged_lab/scripts/play.py
LeggedLab/legged_lab/scripts/train.py
LeggedLab/legged_lab/terrains/__init__.py
LeggedLab/legged_lab/terrains/ray_caster.py
LeggedLab/legged_lab/terrains/ray_caster_cfg.py
LeggedLab/legged_lab/terrains/terrain_generator_cfg.py
LeggedLab/legged_lab/utils/__init__.py
LeggedLab/legged_lab/utils/cli_args.py
LeggedLab/legged_lab/utils/env_utils/__init__.py
LeggedLab/legged_lab/utils/env_utils/scene.py
LeggedLab/legged_lab/utils/keyboard.py
LeggedLab/legged_lab/utils/task_registry.py
LeggedLab/setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `LeggedLab/legged_lab/assets/fftai/gr2` | 1 | 2 KB | [`LeggedLab/legged_lab/assets/fftai/gr2/_OMITTED.md`](./LeggedLab/legged_lab/assets/fftai/gr2/_OMITTED.md) |
| `LeggedLab/legged_lab/assets/fftai/gr2/configuration` | 3 | 17.5 MB | [`LeggedLab/legged_lab/assets/fftai/gr2/configuration/_OMITTED.md`](./LeggedLab/legged_lab/assets/fftai/gr2/configuration/_OMITTED.md) |
| `LeggedLab/legged_lab/assets/unitree/g1` | 1 | 2 KB | [`LeggedLab/legged_lab/assets/unitree/g1/_OMITTED.md`](./LeggedLab/legged_lab/assets/unitree/g1/_OMITTED.md) |
| `LeggedLab/legged_lab/assets/unitree/g1/configuration` | 3 | 27.0 MB | [`LeggedLab/legged_lab/assets/unitree/g1/configuration/_OMITTED.md`](./LeggedLab/legged_lab/assets/unitree/g1/configuration/_OMITTED.md) |
| `LeggedLab/legged_lab/assets/unitree/h1` | 1 | 26.2 MB | [`LeggedLab/legged_lab/assets/unitree/h1/_OMITTED.md`](./LeggedLab/legged_lab/assets/unitree/h1/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
