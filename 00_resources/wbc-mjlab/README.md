# wbc-mjlab — 参考资源

> **来源**：`00_open/wbc-mjlab/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：WBC-Mjlab：mjlab 全身运动跟踪（WBC）共享 MDP，一策略多技能；含 G1 任务/动作库/导出
> **收录**：157 个文件 / 59.6 MB（其中推理策略/模型文件 1 个）
> **已省略**：42 个文件 / 40.9 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（5 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（24 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（3 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（25 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（6 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（94 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （9 个文件）
.github/  （2 个文件）
    workflows/
data/  （16 个文件）
    (直接文件)/
    g1/
demos/  （2 个文件）
    (直接文件)/
    wbc_g1/
docs/  （50 个文件）
    (直接文件)/
    source/
notebooks/  （3 个文件）
    (直接文件)/
src/  （69 个文件）
    wbc_mjlab/
tests/  （6 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 72 |
| `.rst` | 45 |
| `.csv` | 12 |
| `.md` | 9 |
| `(无扩展名)` | 6 |
| `.xml` | 4 |
| `.ipynb` | 2 |
| `.yml` | 2 |
| `.cff` | 1 |
| `.toml` | 1 |
| `.pt` | 1 |
| `.bib` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
.github/workflows/docs.yml
.github/workflows/release.yml
.gitignore
.python-version
CITATION.cff
CONTRIBUTING.md
LICENSE
Makefile
README.md
RELEASING.md
data/README.md
data/g1/.gitkeep
data/g1/README.md
data/g1/samples/README.md
data/g1/samples/dance1_subject1.csv
data/g1/samples/fallAndGetUp1_subject1.csv
data/g1/samples/fight1_subject2.csv
data/g1/samples/fightAndSports1_subject1.csv
data/g1/samples/flip_090_001__A304.csv
data/g1/samples/flip_090_002__A304.csv
data/g1/samples/flip_090_003__A304_M.csv
data/g1/samples/flip_360_009__A416.csv
data/g1/samples/flip_360_011__A416.csv
data/g1/samples/run1_subject2.csv
data/g1/samples/sprint1_subject2.csv
data/g1/samples/walk1_subject1.csv
demos/README.md
demos/wbc_g1/model.pt
docs/BUILDING.md
docs/conf.py
docs/index.rst
docs/source/_static/.gitkeep
docs/source/_static/css/custom.css
docs/source/_static/refs.bib
docs/source/api/export.rst
docs/source/api/extension.rst
docs/source/api/index.rst
docs/source/api/mdp.rst
docs/source/api/presets.rst
docs/source/api/registry.rst
docs/source/architecture.rst
docs/source/concepts/adaptive_sampling.rst
docs/source/concepts/index.rst
docs/source/concepts/modularity.rst
docs/source/concepts/presets_and_tasks.rst
docs/source/concepts/robots_and_extensions.rst
docs/source/contributing.rst
docs/source/data.rst
docs/source/extensions/example_extension.rst
docs/source/extensions/extensions.rst
docs/source/extensions/index.rst
docs/source/extensions/robot_entity.rst
docs/source/installation.rst
docs/source/mdp/actions.rst
docs/source/mdp/events.rst
docs/source/mdp/index.rst
docs/source/mdp/motion_command.rst
docs/source/mdp/observations.rst
docs/source/mdp/rewards.rst
docs/source/mdp/rsi.rst
docs/source/mdp/terminations.rst
docs/source/recipes.rst
docs/source/research.rst
docs/source/roadmap.rst
docs/source/tasks/adding.rst
docs/source/tasks/index.rst
docs/source/tasks/wbc-g1-binary-failure.rst
docs/source/tasks/wbc-g1-se.rst
docs/source/tasks/wbc-g1-zest-se.rst
docs/source/tasks/wbc-g1-zest.rst
docs/source/tasks/wbc-g1.rst
docs/source/troubleshooting.rst
docs/source/usage.rst
docs/source/visualization.rst
docs/source/workflows/demo.rst
docs/source/workflows/deploy.rst
docs/source/workflows/quickstart.rst
docs/source/workflows/training.rst
notebooks/README.md
notebooks/custom_task_train.ipynb
notebooks/demo.ipynb
pyproject.toml
src/wbc_mjlab/__init__.py
src/wbc_mjlab/data_paths.py
src/wbc_mjlab/demo_assets.py
src/wbc_mjlab/deploy_paths.py
src/wbc_mjlab/env/__init__.py
src/wbc_mjlab/env/mdp/__init__.py
src/wbc_mjlab/env/mdp/actions.py
src/wbc_mjlab/env/mdp/assistive_wrench.py
src/wbc_mjlab/env/mdp/commands.py
src/wbc_mjlab/env/mdp/metrics.py
src/wbc_mjlab/env/mdp/observations.py
src/wbc_mjlab/env/mdp/rewards.py
src/wbc_mjlab/env/mdp/sampling.py
src/wbc_mjlab/env/mdp/terminations.py
src/wbc_mjlab/env/mdp/torque_envelope.py
src/wbc_mjlab/env/wbc_env_cfg.py
src/wbc_mjlab/export/__init__.py
src/wbc_mjlab/export/export_cli.py
src/wbc_mjlab/export/policy_bundle.py
src/wbc_mjlab/export/tracking_params_yaml.py
src/wbc_mjlab/export/web_reference.py
src/wbc_mjlab/export/web_reference_bundle.py
src/wbc_mjlab/extension.py
src/wbc_mjlab/mjlab_entry.py
src/wbc_mjlab/motion/__init__.py
src/wbc_mjlab/motion/data_to_npz.py
src/wbc_mjlab/motion/manifest.py
src/wbc_mjlab/motion/motion_export_bundle.py
src/wbc_mjlab/motion/motion_formats.py
src/wbc_mjlab/motion/motion_mirror.py
src/wbc_mjlab/motion/motion_z_debias.py
src/wbc_mjlab/motion/robot_assets.py
src/wbc_mjlab/motion/stack_bundle.py
src/wbc_mjlab/motion/tyro_cli.py
src/wbc_mjlab/presets/__init__.py
src/wbc_mjlab/presets/binary_failure.py
src/wbc_mjlab/presets/se_actor.py
src/wbc_mjlab/presets/wbc.py
src/wbc_mjlab/presets/zest.py
src/wbc_mjlab/rl/__init__.py
src/wbc_mjlab/rl/runner.py
src/wbc_mjlab/robots/__init__.py
src/wbc_mjlab/robots/env.py
src/wbc_mjlab/robots/g1/__init__.py
src/wbc_mjlab/robots/g1/actuators.py
src/wbc_mjlab/robots/g1/base.py
src/wbc_mjlab/robots/g1/constants.py
src/wbc_mjlab/robots/g1/envelope.py
src/wbc_mjlab/robots/g1/rl_cfg.py
src/wbc_mjlab/robots/g1/symmetry.py
src/wbc_mjlab/robots/g1/tasks.py
src/wbc_mjlab/robots/g1/xmls/g1.xml
src/wbc_mjlab/robots/g1/xmls/g1_23dof.xml
src/wbc_mjlab/robots/g1/xmls/scene_g1.xml
src/wbc_mjlab/robots/g1/xmls/scene_g1_23dof.xml
src/wbc_mjlab/robots/ids.py
src/wbc_mjlab/robots/symmetry.py
src/wbc_mjlab/scripts/demo.py
src/wbc_mjlab/scripts/list_envs.py
src/wbc_mjlab/scripts/play.py
src/wbc_mjlab/scripts/plot_rsi_bins.py
src/wbc_mjlab/scripts/train.py
src/wbc_mjlab/scripts/vis_data.py
src/wbc_mjlab/scripts/wbc_cli.py
src/wbc_mjlab/tasks/__init__.py
src/wbc_mjlab/tasks/config.py
src/wbc_mjlab/viewer/__init__.py
src/wbc_mjlab/viewer/motion_vis.py
src/wbc_mjlab/viewer/viser_play.py
tests/smoke_test.py
tests/test_data_paths.py
tests/test_extension.py
tests/test_motion_mirror.py
tests/test_rsi_vis.py
tests/test_web_reference.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 770 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `assets` | 2 | 7.1 MB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `docs/source/_static` | 1 | 119 KB | [`docs/source/_static/_OMITTED.md`](./docs/source/_static/_OMITTED.md) |
| `src/wbc_mjlab/robots/g1/xmls/assets` | 38 | 32.9 MB | [`src/wbc_mjlab/robots/g1/xmls/assets/_OMITTED.md`](./src/wbc_mjlab/robots/g1/xmls/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
