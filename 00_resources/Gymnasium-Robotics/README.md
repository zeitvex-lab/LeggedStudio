# Gymnasium-Robotics — 参考资源

> **来源**：`00_open/Gymnasium-Robotics/`　｜　**类型**：操作与多目标 API 参考（灵巧手 / 迷宫导航）
> **关联机型**：wuji_hand（无极灵巧手）
> **定位**：Farama Gymnasium-Robotics：基于 MuJoCo 的机器人环境集合（Fetch / Shadow 灵巧手 / Adroit / Franka Kitchen / MaMuJoCo / D4RL Maze）；含多目标 GoalEnv API（observation / achieved_goal / desired_goal）与 92 触点触觉观测——灵巧手操作任务、目标条件观测与迷宫导航场景参考
> **收录**：213 个文件 / 1.3 MB（其中推理策略/模型文件 0 个）
> **已省略**：181 个文件 / 294.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（151 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **评测与测试**（14 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（48 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （8 个文件）
.github/  （15 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
    docker/
    workflows/
docs/  （37 个文件）
    (直接文件)/
    _scripts/
    _static/
    content/
    envs/
    release_notes/
gymnasium_robotics/  （134 个文件）
    (直接文件)/
    envs/
    utils/
tests/  （19 个文件）
    (直接文件)/
    envs/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 95 |
| `.xml` | 59 |
| `.md` | 33 |
| `.yml` | 9 |
| `(无扩展名)` | 7 |
| `.template` | 2 |
| `.yaml` | 1 |
| `.cff` | 1 |
| `.rst` | 1 |
| `.toml` | 1 |
| `.bat` | 1 |
| `.txt` | 1 |
| `.dockerfile` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
.github/FUNDING.yml
.github/ISSUE_TEMPLATE/bug.md
.github/ISSUE_TEMPLATE/proposal.md
.github/ISSUE_TEMPLATE/question.md
.github/PULL_REQUEST_TEMPLATE.md
.github/dependabot.yml
.github/docker/entrypoint
.github/docker/py.Dockerfile
.github/stale.yml
.github/workflows/build-docs-dev.yml
.github/workflows/build-docs-version.yml
.github/workflows/build.yml
.github/workflows/manual-build-docs-version.yml
.github/workflows/pre-commit.yml
.github/workflows/pypi-publish.yml
.gitignore
.pre-commit-config.yaml
CITATION.cff
CODE_OF_CONDUCT.rst
LICENSE
README.md
docs/404.md
docs/LICENSE
docs/Makefile
docs/README.md
docs/_scripts/gen_envs_display.py
docs/_scripts/gen_gifs.py
docs/_scripts/gen_mds.py
docs/_scripts/move_404.py
docs/_scripts/utils.py
docs/_static/css/env_pages.css
docs/conf.py
docs/content/installation.md
docs/content/multi-goal_api.md
docs/envs/MaMuJoCo/figures/credits
docs/envs/MaMuJoCo/index.md
docs/envs/MaMuJoCo/ma_ant.md
docs/envs/MaMuJoCo/ma_coupled_half_cheetah.md
docs/envs/MaMuJoCo/ma_half_cheetah.md
docs/envs/MaMuJoCo/ma_hopper.md
docs/envs/MaMuJoCo/ma_humanoid.md
docs/envs/MaMuJoCo/ma_humanoid_standup.md
docs/envs/MaMuJoCo/ma_multiagentswimmer.md
docs/envs/MaMuJoCo/ma_pusher.md
docs/envs/MaMuJoCo/ma_reacher.md
docs/envs/MaMuJoCo/ma_single.md
docs/envs/MaMuJoCo/ma_swimmer.md
docs/envs/MaMuJoCo/ma_walker2d.md
docs/envs/adroit_hand/index.md
docs/envs/fetch/index.md
docs/envs/franka_kitchen/index.md
docs/envs/maze/index.md
docs/envs/shadow_dexterous_hand/index.md
docs/index.md
docs/make.bat
docs/release_notes.md
docs/release_notes/index.md
docs/requirements.txt
gymnasium_robotics/__init__.py
gymnasium_robotics/core.py
gymnasium_robotics/envs/__init__.py
gymnasium_robotics/envs/adroit_hand/__init__.py
gymnasium_robotics/envs/adroit_hand/adroit_door.py
gymnasium_robotics/envs/adroit_hand/adroit_hammer.py
gymnasium_robotics/envs/adroit_hand/adroit_pen.py
gymnasium_robotics/envs/adroit_hand/adroit_relocate.py
gymnasium_robotics/envs/assets/LICENSE.md
gymnasium_robotics/envs/assets/adroit_hand/adroit_assets.xml
gymnasium_robotics/envs/assets/adroit_hand/adroit_door.xml
gymnasium_robotics/envs/assets/adroit_hand/adroit_hammer.xml
gymnasium_robotics/envs/assets/adroit_hand/adroit_model.xml
gymnasium_robotics/envs/assets/adroit_hand/adroit_pen.xml
gymnasium_robotics/envs/assets/adroit_hand/adroit_relocate.xml
gymnasium_robotics/envs/assets/fetch/pick_and_place.xml
gymnasium_robotics/envs/assets/fetch/push.xml
gymnasium_robotics/envs/assets/fetch/reach.xml
gymnasium_robotics/envs/assets/fetch/robot.xml
gymnasium_robotics/envs/assets/fetch/shared.xml
gymnasium_robotics/envs/assets/fetch/slide.xml
gymnasium_robotics/envs/assets/hand/manipulate_block.xml
gymnasium_robotics/envs/assets/hand/manipulate_block_touch_sensors.xml
gymnasium_robotics/envs/assets/hand/manipulate_egg.xml
gymnasium_robotics/envs/assets/hand/manipulate_egg_touch_sensors.xml
gymnasium_robotics/envs/assets/hand/manipulate_pen.xml
gymnasium_robotics/envs/assets/hand/manipulate_pen_touch_sensors.xml
gymnasium_robotics/envs/assets/hand/reach.xml
gymnasium_robotics/envs/assets/hand/robot.xml
gymnasium_robotics/envs/assets/hand/robot_touch_sensors_92.xml
gymnasium_robotics/envs/assets/hand/shared.xml
gymnasium_robotics/envs/assets/hand/shared_asset.xml
gymnasium_robotics/envs/assets/hand/shared_touch_sensors_92.xml
gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/LICENSE.md
gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/actuator.xml
gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/assets.xml
gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/basic_scene.xml
gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/franka_config.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/LICENSE.md
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/basic_scene.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/backwall_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/backwall_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/counters_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/counters_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/hingecabinet_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/hingecabinet_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/kettle_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/kettle_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/microwave_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/microwave_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/oven_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/oven_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/slidecabinet_asset.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/item_assets/slidecabinet_chain.xml
gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/kitchen_env_model.xml
gymnasium_robotics/envs/assets/point/point.xml
gymnasium_robotics/envs/fetch/__init__.py
gymnasium_robotics/envs/fetch/fetch_env.py
gymnasium_robotics/envs/fetch/pick_and_place.py
gymnasium_robotics/envs/fetch/push.py
gymnasium_robotics/envs/fetch/reach.py
gymnasium_robotics/envs/fetch/slide.py
gymnasium_robotics/envs/franka_kitchen/__init__.py
gymnasium_robotics/envs/franka_kitchen/franka_env.py
gymnasium_robotics/envs/franka_kitchen/kitchen_env.py
gymnasium_robotics/envs/franka_kitchen/utils.py
gymnasium_robotics/envs/maze/__init__.py
gymnasium_robotics/envs/maze/ant_maze_v3.py
gymnasium_robotics/envs/maze/ant_maze_v4.py
gymnasium_robotics/envs/maze/ant_maze_v5.py
gymnasium_robotics/envs/maze/maps.py
gymnasium_robotics/envs/maze/maze.py
gymnasium_robotics/envs/maze/maze_v4.py
gymnasium_robotics/envs/maze/point.py
gymnasium_robotics/envs/maze/point_maze.py
gymnasium_robotics/envs/mujoco/__init__.py
gymnasium_robotics/envs/mujoco/ant_v2.py
gymnasium_robotics/envs/mujoco/ant_v3.py
gymnasium_robotics/envs/mujoco/assets/ant.xml
gymnasium_robotics/envs/mujoco/assets/half_cheetah.xml
gymnasium_robotics/envs/mujoco/assets/hopper.xml
gymnasium_robotics/envs/mujoco/assets/humanoid.xml
gymnasium_robotics/envs/mujoco/assets/humanoidstandup.xml
gymnasium_robotics/envs/mujoco/assets/inverted_double_pendulum.xml
gymnasium_robotics/envs/mujoco/assets/inverted_pendulum.xml
gymnasium_robotics/envs/mujoco/assets/point.xml
gymnasium_robotics/envs/mujoco/assets/pusher.xml
gymnasium_robotics/envs/mujoco/assets/reacher.xml
gymnasium_robotics/envs/mujoco/assets/swimmer.xml
gymnasium_robotics/envs/mujoco/assets/walker2d.xml
gymnasium_robotics/envs/mujoco/half_cheetah_v2.py
gymnasium_robotics/envs/mujoco/half_cheetah_v3.py
gymnasium_robotics/envs/mujoco/hopper_v2.py
gymnasium_robotics/envs/mujoco/hopper_v3.py
gymnasium_robotics/envs/mujoco/humanoid_v2.py
gymnasium_robotics/envs/mujoco/humanoid_v3.py
gymnasium_robotics/envs/mujoco/humanoidstandup_v2.py
gymnasium_robotics/envs/mujoco/inverted_double_pendulum_v2.py
gymnasium_robotics/envs/mujoco/inverted_pendulum_v2.py
gymnasium_robotics/envs/mujoco/mujoco_py_env.py
gymnasium_robotics/envs/mujoco/pusher_v2.py
gymnasium_robotics/envs/mujoco/reacher_v2.py
gymnasium_robotics/envs/mujoco/swimmer_v2.py
gymnasium_robotics/envs/mujoco/swimmer_v3.py
gymnasium_robotics/envs/mujoco/walker2d_v2.py
gymnasium_robotics/envs/mujoco/walker2d_v3.py
gymnasium_robotics/envs/multiagent_mujoco/LICENSE
gymnasium_robotics/envs/multiagent_mujoco/__init__.py
gymnasium_robotics/envs/multiagent_mujoco/assets/coupled_half_cheetah.xml
gymnasium_robotics/envs/multiagent_mujoco/assets/many_segment_ant.xml.template
gymnasium_robotics/envs/multiagent_mujoco/assets/many_segment_swimmer.xml.template
gymnasium_robotics/envs/multiagent_mujoco/coupled_half_cheetah.py
gymnasium_robotics/envs/multiagent_mujoco/mamujoco_v1.py
gymnasium_robotics/envs/multiagent_mujoco/many_segment_ant.py
gymnasium_robotics/envs/multiagent_mujoco/many_segment_swimmer.py
gymnasium_robotics/envs/multiagent_mujoco/mujoco_multi.py
gymnasium_robotics/envs/multiagent_mujoco/obsk.py
gymnasium_robotics/envs/robot_env.py
gymnasium_robotics/envs/shadow_dexterous_hand/__init__.py
gymnasium_robotics/envs/shadow_dexterous_hand/hand_env.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_block.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_block_touch_sensors.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_egg.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_egg_touch_sensors.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_pen.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_pen_touch_sensors.py
gymnasium_robotics/envs/shadow_dexterous_hand/manipulate_touch_sensors.py
gymnasium_robotics/envs/shadow_dexterous_hand/reach.py
gymnasium_robotics/utils/__init__.py
gymnasium_robotics/utils/mujoco_py_utils.py
gymnasium_robotics/utils/mujoco_utils.py
gymnasium_robotics/utils/rotations.py
pyproject.toml
setup.py
tests/__init__.py
tests/envs/MaMuJoCo/test_MaMuJoCo.py
tests/envs/__init__.py
tests/envs/adroit_hand/test_adroit_hammer.py
tests/envs/adroit_hand/test_adroit_relocate.py
tests/envs/franka_kitchen/test_kitchen_env.py
tests/envs/hand/__init__.py
tests/envs/hand/test_manipulate.py
tests/envs/hand/test_manipulate_touch_sensors.py
tests/envs/hand/test_reach.py
tests/envs/maze/test_ant_maze.py
tests/envs/maze/test_point_maze.py
tests/envs/mujoco/__init__.py
tests/envs/mujoco/test_mujoco_v3.py
tests/envs/mujoco/test_mujoco_v5.py
tests/test_envs.py
tests/test_goal_env_api.py
tests/test_mujoco_utils.py
tests/utils.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs` | 1 | 128 KB | [`docs/_OMITTED.md`](./docs/_OMITTED.md) |
| `docs/_static/img` | 7 | 180 KB | [`docs/_static/img/_OMITTED.md`](./docs/_static/img/_OMITTED.md) |
| `docs/_static/videos/adroit_hand` | 4 | 140.1 MB | [`docs/_static/videos/adroit_hand/_OMITTED.md`](./docs/_static/videos/adroit_hand/_OMITTED.md) |
| `docs/_static/videos/fetch` | 4 | 17.6 MB | [`docs/_static/videos/fetch/_OMITTED.md`](./docs/_static/videos/fetch/_OMITTED.md) |
| `docs/_static/videos/franka_kitchen` | 1 | 19.9 MB | [`docs/_static/videos/franka_kitchen/_OMITTED.md`](./docs/_static/videos/franka_kitchen/_OMITTED.md) |
| `docs/_static/videos/maze` | 2 | 33.0 MB | [`docs/_static/videos/maze/_OMITTED.md`](./docs/_static/videos/maze/_OMITTED.md) |
| `docs/_static/videos/shadow_dexterous_hand` | 7 | 38.5 MB | [`docs/_static/videos/shadow_dexterous_hand/_OMITTED.md`](./docs/_static/videos/shadow_dexterous_hand/_OMITTED.md) |
| `docs/envs/MaMuJoCo/figures` | 26 | 981 KB | [`docs/envs/MaMuJoCo/figures/_OMITTED.md`](./docs/envs/MaMuJoCo/figures/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/adroit_hand/resources/meshes` | 29 | 22.1 MB | [`gymnasium_robotics/envs/assets/adroit_hand/resources/meshes/_OMITTED.md`](./gymnasium_robotics/envs/assets/adroit_hand/resources/meshes/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/adroit_hand/resources/textures` | 9 | 3.9 MB | [`gymnasium_robotics/envs/assets/adroit_hand/resources/textures/_OMITTED.md`](./gymnasium_robotics/envs/assets/adroit_hand/resources/textures/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/meshes/collision` | 10 | 115 KB | [`gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/meshes/collision/_OMITTED.md`](./gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/meshes/collision/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/meshes/visual` | 10 | 6.4 MB | [`gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/meshes/visual/_OMITTED.md`](./gymnasium_robotics/envs/assets/kitchen_franka/franka_assets/meshes/visual/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/meshes` | 33 | 397 KB | [`gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/meshes/_OMITTED.md`](./gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/meshes/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/textures` | 6 | 7.6 MB | [`gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/textures/_OMITTED.md`](./gymnasium_robotics/envs/assets/kitchen_franka/kitchen_assets/textures/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/stls/fetch` | 18 | 1.6 MB | [`gymnasium_robotics/envs/assets/stls/fetch/_OMITTED.md`](./gymnasium_robotics/envs/assets/stls/fetch/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/stls/hand` | 12 | 1.6 MB | [`gymnasium_robotics/envs/assets/stls/hand/_OMITTED.md`](./gymnasium_robotics/envs/assets/stls/hand/_OMITTED.md) |
| `gymnasium_robotics/envs/assets/textures` | 2 | 56 KB | [`gymnasium_robotics/envs/assets/textures/_OMITTED.md`](./gymnasium_robotics/envs/assets/textures/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
