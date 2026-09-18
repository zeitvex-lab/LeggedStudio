# LainLab — 参考资源

> **来源**：`00_open/LainLab/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_g1（宇树 G1 人形）
> **定位**：LainLab：mjlab 1.6 多厂商资产/任务/部署层（go2 skills 全套 + OpenDoge 自研；Apache-2.0）
> **收录**：296 个文件 / 49.1 MB（其中推理策略/模型文件 8 个）
> **已省略**：303 个文件 / 259.7 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（41 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（76 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（9 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（47 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（12 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（111 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （8 个文件）
docs/  （2 个文件）
    (直接文件)/
playground/  （18 个文件）
    (直接文件)/
    public/
    scripts/
    src/
simulate/  （16 个文件）
    (直接文件)/
    src/
src/  （236 个文件）
    (直接文件)/
    assets/
    tasks/
    workbench/
tests/  （15 个文件）
    (直接文件)/
typings/  （1 个文件）
    mujoco/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 185 |
| `.txt` | 18 |
| `.xml` | 16 |
| `.md` | 12 |
| `.js` | 8 |
| `.onnx` | 8 |
| `.npz` | 8 |
| `(无扩展名)` | 7 |
| `.json` | 5 |
| `.h` | 5 |
| `.html` | 4 |
| `.css` | 4 |
| `.cc` | 3 |
| `.yaml` | 2 |
| `.bvh` | 2 |

## 文件索引（项目内相对路径）

```text
.gitignore
.pre-commit-config.yaml
.python-version
CHANGELOG.md
LICENSE
Makefile
README.md
docs/go2_migration_matrix.md
docs/workbench.md
playground/.gitignore
playground/README.md
playground/index.html
playground/package-lock.json
playground/package.json
playground/public/policies/go2-amp-cts.onnx
playground/public/policies/go2-arena-flat.onnx
playground/public/policies/go2-dreamwaq.onnx
playground/public/policies/go2-handstand.onnx
playground/public/policies/go2-jump.onnx
playground/public/policies/go2-rear-stand.onnx
playground/public/policies/go2-spring-jump.onnx
playground/public/policies/go2-trot.onnx
playground/scripts/export_policies.py
playground/scripts/prepare-assets.mjs
playground/src/main.js
playground/src/style.css
playground/vite.config.js
pyproject.toml
simulate/CMakeLists.txt
simulate/README.md
simulate/config.yaml
simulate/src/joystick/LICENSE-2.0.txt
simulate/src/joystick/joystick.cc
simulate/src/joystick/joystick.h
simulate/src/joystick/jstest.cc
simulate/src/joystick/readme.md
simulate/src/lodepng/LICENSE
simulate/src/lodepng/README.md
simulate/src/lodepng/lodepng.cpp
simulate/src/lodepng/lodepng.h
simulate/src/main.cc
simulate/src/param.h
simulate/src/physics_joystick.h
simulate/src/unitree_sdk2_bridge.h
src/__init__.py
src/assets/__init__.py
src/assets/motions/README.md
src/assets/motions/__init__.py
src/assets/motions/converted/g1_dance1_subject2_50fps.npz
src/assets/motions/examples/motions/live-check-42071f.npz
src/assets/motions/examples/motions/pkl-check-ed1877.npz
src/assets/motions/examples/motions/visual-check-206f20.npz
src/assets/motions/examples/pkl-preview-check.pkl
src/assets/motions/examples/smoke.bvh
src/assets/motions/examples/smoke.npz
src/assets/motions/examples/visual-check.bvh
src/assets/motions/g1/dance1_subject2.csv
src/assets/motions/g1_23dof/dance1_subject2.csv
src/assets/motions/generated/g1/dance1_subject2_1aa35366cfe3.npz
src/assets/motions/generated/g1/dance1_subject2_57b86c7cca37.npz
src/assets/motions/generated/g1/visual-check_8ac4ad656f23.npz
src/assets/motions/go2_amp/backward.txt
src/assets/motions/go2_amp/forward.txt
src/assets/motions/go2_amp/forward_left.txt
src/assets/motions/go2_amp/forward_right.txt
src/assets/motions/go2_amp/left.txt
src/assets/motions/go2_amp/left_new.txt
src/assets/motions/go2_amp/right.txt
src/assets/motions/go2_amp/right_new.txt
src/assets/motions/go2_amp/rotate.txt
src/assets/motions/go2_amp/rotate_inverse.txt
src/assets/motions/go2_amp/stand.txt
src/assets/motions/go2_amp/turn_left.txt
src/assets/motions/go2_amp/turn_right.txt
src/assets/robots/__init__.py
src/assets/robots/opendoge/README.md
src/assets/robots/opendoge/__init__.py
src/assets/robots/opendoge/convert_urdf.py
src/assets/robots/opendoge/opendoge_constants.py
src/assets/robots/opendoge/urdf/opendoge.urdf
src/assets/robots/opendoge/xmls/opendoge.xml
src/assets/robots/opendoge/xmls/scene_opendoge.xml
src/assets/robots/unitree_a2/__init__.py
src/assets/robots/unitree_a2/a2_constants.py
src/assets/robots/unitree_a2/xmls/a2.xml
src/assets/robots/unitree_a2/xmls/scene_a2.xml
src/assets/robots/unitree_as2/__init__.py
src/assets/robots/unitree_as2/as2_constants.py
src/assets/robots/unitree_as2/xmls/as2.xml
src/assets/robots/unitree_g1/__init__.py
src/assets/robots/unitree_g1/g1_23dof_constants.py
src/assets/robots/unitree_g1/g1_constants.py
src/assets/robots/unitree_g1/xmls/g1.xml
src/assets/robots/unitree_g1/xmls/g1_23dof.xml
src/assets/robots/unitree_g1/xmls/scene_g1.xml
src/assets/robots/unitree_g1/xmls/scene_g1_23dof.xml
src/assets/robots/unitree_go2/__init__.py
src/assets/robots/unitree_go2/go2_constants.py
src/assets/robots/unitree_go2/xmls/go2.xml
src/assets/robots/unitree_go2/xmls/scene_go2.xml
src/assets/robots/unitree_h1_2/__init__.py
src/assets/robots/unitree_h1_2/h1_2_constants.py
src/assets/robots/unitree_h1_2/xmls/h1_2.xml
src/assets/robots/unitree_h1_2/xmls/scene_h1_2.xml
src/assets/robots/unitree_h2/__init__.py
src/assets/robots/unitree_h2/h2_constants.py
src/assets/robots/unitree_h2/xmls/h2.xml
src/assets/robots/unitree_r1/__init__.py
src/assets/robots/unitree_r1/r1_constants.py
src/assets/robots/unitree_r1/xmls/r1.xml
src/cli.py
src/gmr_conversion.py
src/motion_conversion.py
src/py.typed
src/tasks/__init__.py
src/tasks/amp/__init__.py
src/tasks/amp/core.py
src/tasks/rl.py
src/tasks/robots/__init__.py
src/tasks/robots/common.py
src/tasks/robots/g1/__init__.py
src/tasks/robots/g1/tracking.py
src/tasks/robots/go2/__init__.py
src/tasks/robots/go2/skills/__init__.py
src/tasks/robots/go2/skills/amp_dreamwaq/__init__.py
src/tasks/robots/go2/skills/amp_dreamwaq/commands.py
src/tasks/robots/go2/skills/amp_dreamwaq/config.py
src/tasks/robots/go2/skills/amp_dreamwaq/mdp.py
src/tasks/robots/go2/skills/amp_dreamwaq/motion.py
src/tasks/robots/go2/skills/amp_dreamwaq/rl.py
src/tasks/robots/go2/skills/backflip/__init__.py
src/tasks/robots/go2/skills/backflip/config.py
src/tasks/robots/go2/skills/backflip/mdp/__init__.py
src/tasks/robots/go2/skills/backflip/mdp/commands.py
src/tasks/robots/go2/skills/backflip/mdp/events.py
src/tasks/robots/go2/skills/backflip/mdp/observations.py
src/tasks/robots/go2/skills/backflip/mdp/rewards.py
src/tasks/robots/go2/skills/backflip/mdp/terminations.py
src/tasks/robots/go2/skills/backflip/profile.py
src/tasks/robots/go2/skills/configs/__init__.py
src/tasks/robots/go2/skills/configs/amp_dreamwaq.py
src/tasks/robots/go2/skills/configs/backflip.py
src/tasks/robots/go2/skills/configs/cts.py
src/tasks/robots/go2/skills/configs/dreamwaq.py
src/tasks/robots/go2/skills/configs/hand_stand.py
src/tasks/robots/go2/skills/configs/jump.py
src/tasks/robots/go2/skills/configs/rear_stand.py
src/tasks/robots/go2/skills/configs/spring_jump.py
src/tasks/robots/go2/skills/configs/trot.py
src/tasks/robots/go2/skills/configs/ts.py
src/tasks/robots/go2/skills/cts/__init__.py
src/tasks/robots/go2/skills/cts/config.py
src/tasks/robots/go2/skills/cts/mdp/__init__.py
src/tasks/robots/go2/skills/cts/mdp/commands.py
src/tasks/robots/go2/skills/cts/mdp/events.py
src/tasks/robots/go2/skills/cts/mdp/observations.py
src/tasks/robots/go2/skills/cts/mdp/rewards.py
src/tasks/robots/go2/skills/cts/profile.py
src/tasks/robots/go2/skills/cts/rl.py
src/tasks/robots/go2/skills/dreamwaq/__init__.py
src/tasks/robots/go2/skills/dreamwaq/config.py
src/tasks/robots/go2/skills/dreamwaq/mdp/__init__.py
src/tasks/robots/go2/skills/dreamwaq/mdp/commands.py
src/tasks/robots/go2/skills/dreamwaq/mdp/observations.py
src/tasks/robots/go2/skills/dreamwaq/mdp/rewards.py
src/tasks/robots/go2/skills/dreamwaq/mdp/rl.py
src/tasks/robots/go2/skills/dreamwaq/profile.py
src/tasks/robots/go2/skills/hand_stand/__init__.py
src/tasks/robots/go2/skills/hand_stand/config.py
src/tasks/robots/go2/skills/hand_stand/mdp/__init__.py
src/tasks/robots/go2/skills/hand_stand/mdp/commands.py
src/tasks/robots/go2/skills/hand_stand/mdp/events.py
src/tasks/robots/go2/skills/hand_stand/mdp/observations.py
src/tasks/robots/go2/skills/hand_stand/mdp/rewards.py
src/tasks/robots/go2/skills/hand_stand/profile.py
src/tasks/robots/go2/skills/jump/__init__.py
src/tasks/robots/go2/skills/jump/config.py
src/tasks/robots/go2/skills/jump/mdp/__init__.py
src/tasks/robots/go2/skills/jump/mdp/commands.py
src/tasks/robots/go2/skills/jump/mdp/curriculums.py
src/tasks/robots/go2/skills/jump/mdp/events.py
src/tasks/robots/go2/skills/jump/mdp/observations.py
src/tasks/robots/go2/skills/jump/mdp/rewards.py
src/tasks/robots/go2/skills/jump/profile.py
src/tasks/robots/go2/skills/rear_stand/__init__.py
src/tasks/robots/go2/skills/rear_stand/config.py
src/tasks/robots/go2/skills/rear_stand/mdp/__init__.py
src/tasks/robots/go2/skills/rear_stand/mdp/commands.py
src/tasks/robots/go2/skills/rear_stand/mdp/events.py
src/tasks/robots/go2/skills/rear_stand/mdp/observations.py
src/tasks/robots/go2/skills/rear_stand/mdp/rewards.py
src/tasks/robots/go2/skills/rear_stand/mdp/symmetry.py
src/tasks/robots/go2/skills/rear_stand/profile.py
src/tasks/robots/go2/skills/shared/__init__.py
src/tasks/robots/go2/skills/shared/actions.py
src/tasks/robots/go2/skills/shared/contacts.py
src/tasks/robots/go2/skills/shared/events.py
src/tasks/robots/go2/skills/shared/rl.py
src/tasks/robots/go2/skills/shared/robot.py
src/tasks/robots/go2/skills/shared/sensors.py
src/tasks/robots/go2/skills/shared/terminations.py
src/tasks/robots/go2/skills/spring_jump/__init__.py
src/tasks/robots/go2/skills/spring_jump/config.py
src/tasks/robots/go2/skills/spring_jump/mdp/__init__.py
src/tasks/robots/go2/skills/spring_jump/mdp/base_commands.py
src/tasks/robots/go2/skills/spring_jump/mdp/base_observations.py
src/tasks/robots/go2/skills/spring_jump/mdp/commands.py
src/tasks/robots/go2/skills/spring_jump/mdp/events.py
src/tasks/robots/go2/skills/spring_jump/mdp/observations.py
src/tasks/robots/go2/skills/spring_jump/mdp/rewards.py
src/tasks/robots/go2/skills/spring_jump/mdp/symmetry.py
src/tasks/robots/go2/skills/spring_jump/mdp/terminations.py
src/tasks/robots/go2/skills/spring_jump/profile.py
src/tasks/robots/go2/skills/trot/__init__.py
src/tasks/robots/go2/skills/trot/config.py
src/tasks/robots/go2/skills/trot/mdp/__init__.py
src/tasks/robots/go2/skills/trot/mdp/commands.py
src/tasks/robots/go2/skills/trot/mdp/curriculums.py
src/tasks/robots/go2/skills/trot/mdp/events.py
src/tasks/robots/go2/skills/trot/mdp/observations.py
src/tasks/robots/go2/skills/trot/mdp/rewards.py
src/tasks/robots/go2/skills/trot/profile.py
src/tasks/robots/go2/skills/ts/__init__.py
src/tasks/robots/go2/skills/ts/config.py
src/tasks/robots/go2/skills/ts/mdp/__init__.py
src/tasks/robots/go2/skills/ts/mdp/events.py
src/tasks/robots/go2/skills/ts/mdp/observations.py
src/tasks/robots/go2/skills/ts/mdp/rewards.py
src/tasks/robots/go2/skills/ts/profile.py
src/tasks/robots/go2/skills/ts/rl.py
src/tasks/robots/go2/velocity.py
src/tasks/robots/opendoge/__init__.py
src/tasks/robots/opendoge/velocity.py
src/tasks/robots/unitree/__init__.py
src/tasks/robots/unitree/velocity.py
src/tasks/tracking/__init__.py
src/tasks/tracking/core.py
src/tasks/velocity/__init__.py
src/tasks/velocity/core.py
src/webui.py
src/workbench/__init__.py
src/workbench/catalog.py
src/workbench/gmr/LICENSE
src/workbench/gmr/NOTICE.md
src/workbench/gmr/__init__.py
src/workbench/gmr/assets/g1_mocap_29dof.xml
src/workbench/gmr/bvh_to_g1.json
src/workbench/gmr/motion_retarget.py
src/workbench/gmr/params.py
src/workbench/gmr/utils/__init__.py
src/workbench/gmr/utils/lafan1.py
src/workbench/gmr/utils/lafan_vendor/__init__.py
src/workbench/gmr/utils/lafan_vendor/extract.py
src/workbench/gmr/utils/lafan_vendor/license.txt
src/workbench/gmr/utils/lafan_vendor/utils.py
src/workbench/models.py
src/workbench/motion_library.py
src/workbench/motion_preview.py
src/workbench/npz_preview.py
src/workbench/retarget.py
src/workbench/server.py
src/workbench/services.py
src/workbench/static/app.js
src/workbench/static/index.html
src/workbench/static/style.css
src/workbench/static/viewer/THREE_LICENSE.txt
src/workbench/static/viewer/assets/index-050de542.js
src/workbench/static/viewer/assets/index-7f0a639c.css
src/workbench/static/viewer/assets/motion-9fd4ec41.js
src/workbench/static/viewer/index.html
src/workbench/viewer/README.md
src/workbench/viewer/index.html
src/workbench/viewer/package-lock.json
src/workbench/viewer/package.json
src/workbench/viewer/public/THREE_LICENSE.txt
src/workbench/viewer/src/main.js
src/workbench/viewer/src/motion.js
src/workbench/viewer/src/style.css
src/workbench/viewer/vite.config.js
src/workbench/worker.py
tests/test_amp_dreamwaq.py
tests/test_assets.py
tests/test_cts.py
tests/test_go2_rear_stand_symmetry.py
tests/test_go2_skill_configs.py
tests/test_go2_skill_smoke.py
tests/test_motion_library.py
tests/test_motion_preview.py
tests/test_npz_preview.py
tests/test_opendoge_smoke.py
tests/test_tasks.py
tests/test_ts.py
tests/test_velocity_core.py
tests/test_workbench.py
tests/test_workbench_models.py
typings/mujoco/__init__.pyi
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 802 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `src/assets/robots/opendoge/xmls/assets` | 13 | 18.0 MB | [`src/assets/robots/opendoge/xmls/assets/_OMITTED.md`](./src/assets/robots/opendoge/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_a2/xmls/assets` | 17 | 14.1 MB | [`src/assets/robots/unitree_a2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_a2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_as2/xmls/assets` | 18 | 65.5 MB | [`src/assets/robots/unitree_as2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_as2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_g1/xmls/assets` | 38 | 32.9 MB | [`src/assets/robots/unitree_g1/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_g1/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_go2/xmls/assets` | 16 | 27.8 MB | [`src/assets/robots/unitree_go2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_go2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_h1_2/xmls/assets` | 90 | 47.9 MB | [`src/assets/robots/unitree_h1_2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_h1_2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_h2/xmls/assets` | 32 | 12.4 MB | [`src/assets/robots/unitree_h2/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_h2/xmls/assets/_OMITTED.md) |
| `src/assets/robots/unitree_r1/xmls/assets` | 43 | 21.6 MB | [`src/assets/robots/unitree_r1/xmls/assets/_OMITTED.md`](./src/assets/robots/unitree_r1/xmls/assets/_OMITTED.md) |
| `src/workbench/gmr/assets/meshes` | 35 | 18.8 MB | [`src/workbench/gmr/assets/meshes/_OMITTED.md`](./src/workbench/gmr/assets/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
