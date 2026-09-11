# robo_re — 参考资源

> **来源**：`00_open/robo_re/`　｜　**类型**：参考项目
> **关联机型**：unitree_g1（宇树 G1 人形）
> **定位**：G1 人形 RL 工程
> **收录**：154 个文件 / 100.2 MB（其中推理策略/模型文件 0 个）
> **已省略**：1393 个文件 / 1646.3 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（26 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **动作与运动数据**（128 个）：动作与运动数据：重定向配置、参考动作、步态数据

## 目录构成

```text
robot_retargeter/  （154 个文件）
    (直接文件)/
    asset/
    bash/
    config/
    dataset/
    scripts/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.csv` | 45 |
| `.xml` | 43 |
| `.urdf` | 26 |
| `.yaml` | 24 |
| `.py` | 6 |
| `(无扩展名)` | 2 |
| `.md` | 2 |
| `.sh` | 2 |
| `.npz` | 2 |
| `.txt` | 1 |
| `.mtl` | 1 |

## 文件索引（项目内相对路径）

```text
robot_retargeter/.gitattributes
robot_retargeter/.gitignore
robot_retargeter/README.md
robot_retargeter/README_zh.md
robot_retargeter/asset/robot/DR02/mjcf/pro/DR02_pro.xml
robot_retargeter/asset/robot/HU_D04_description/xml/HU_D04_01.xml
robot_retargeter/asset/robot/a2_description/a2.xml
robot_retargeter/asset/robot/a2_description/urdf/a2.urdf
robot_retargeter/asset/robot/a2w_description/a2_wheel.urdf
robot_retargeter/asset/robot/a2w_description/a2_wheel.xml
robot_retargeter/asset/robot/agibot_x2/urdf/x2_fist.urdf
robot_retargeter/asset/robot/agibot_x2/urdf/x2_fist.xml
robot_retargeter/asset/robot/agibot_x2/urdf/x2_hand.urdf
robot_retargeter/asset/robot/agibot_x2/urdf/x2_hand.xml
robot_retargeter/asset/robot/agibot_x2/urdf/x2_ultra.urdf
robot_retargeter/asset/robot/agibot_x2/urdf/x2_ultra.xml
robot_retargeter/asset/robot/agibot_x2/urdf/x2_ultra_simple_collision.urdf
robot_retargeter/asset/robot/agibot_x2/x2_ultra.xml
robot_retargeter/asset/robot/biped_s53/xml/biped_s53.xml
robot_retargeter/asset/robot/biped_s53/xml/scene.xml
robot_retargeter/asset/robot/booster_t1/T1_locomotion.urdf
robot_retargeter/asset/robot/booster_t1/T1_locomotion.xml
robot_retargeter/asset/robot/booster_t1/T1_serial.urdf
robot_retargeter/asset/robot/booster_t1/T1_serial.xml
robot_retargeter/asset/robot/dex_evt/urdf/tiangong2dex_29.urdf
robot_retargeter/asset/robot/dex_evt/urdf/tiangong2dex_29.xml
robot_retargeter/asset/robot/g1_d_description/g1_d.urdf
robot_retargeter/asset/robot/g1_d_description/g1_d.xml
robot_retargeter/asset/robot/g1_description/mjcf/g1.xml
robot_retargeter/asset/robot/h1_2_description/h1_2.urdf
robot_retargeter/asset/robot/h1_2_description/h1_2.xml
robot_retargeter/asset/robot/h1_2_description/h1_2_handless.urdf
robot_retargeter/asset/robot/h1_2_description/h1_2_handless.xml
robot_retargeter/asset/robot/h1_2_description/h1_2_with_FTP_hand.urdf
robot_retargeter/asset/robot/h1_description/mjcf/h1.xml
robot_retargeter/asset/robot/h1_description/mjcf/h1_with_hand.xml
robot_retargeter/asset/robot/h1_description/mjcf/scene.xml
robot_retargeter/asset/robot/h1_description/package.xml
robot_retargeter/asset/robot/h1_description/urdf/h1.urdf
robot_retargeter/asset/robot/h1_description/urdf/h1_with_hand.urdf
robot_retargeter/asset/robot/h2_description/H2.urdf
robot_retargeter/asset/robot/h2_description/H2.xml
robot_retargeter/asset/robot/h2_description/H2_dae.urdf
robot_retargeter/asset/robot/hightorque_hi/hi_25dof.urdf
robot_retargeter/asset/robot/hightorque_hi/hi_25dof.xml
robot_retargeter/asset/robot/jaka_pi/Khan_mini.xml
robot_retargeter/asset/robot/jaka_pi/Khan_mini_simplified.urdf
robot_retargeter/asset/robot/jaka_pi/Khan_mini_simplified.xml
robot_retargeter/asset/robot/jaka_pi/meshes/Khan_mini.urdf
robot_retargeter/asset/robot/l7_29dof_neck_fixed/l7_29dof_neck_fixed.xml
robot_retargeter/asset/robot/noetix_N2/mjcf/n2_18dof.xml
robot_retargeter/asset/robot/noetix_e1/mjcf/e1_24dof.xml
robot_retargeter/asset/robot/pi_plus_24dof/urdf/pi_plus_24dof.urdf
robot_retargeter/asset/robot/pi_plus_24dof/xml/pi_plus_20dof.xml
robot_retargeter/asset/robot/pm01_edu/urdf/serial_pm01_edu.urdf
robot_retargeter/asset/robot/pm01_edu/xml/assets.xml
robot_retargeter/asset/robot/pm01_edu/xml/serial_actuators.xml
robot_retargeter/asset/robot/pm01_edu/xml/serial_links.xml
robot_retargeter/asset/robot/pm01_edu/xml/serial_pm01_edu.xml
robot_retargeter/asset/robot/pm01_edu/xml/serial_sensors.xml
robot_retargeter/asset/robot/pnd_adam_lite/adam_lite.urdf
robot_retargeter/asset/robot/pnd_adam_lite/adam_lite.xml
robot_retargeter/asset/robot/pnd_adam_lite/assets/material.mtl
robot_retargeter/asset/robot/pnd_adam_lite/scene.xml
robot_retargeter/asset/robot/r1_description/R1.urdf
robot_retargeter/asset/robot/r1_description/R1.xml
robot_retargeter/asset/robot/t800/urdf/serial_t800.urdf
robot_retargeter/asset/robot/t800/xml/assets.xml
robot_retargeter/asset/robot/t800/xml/serial_actuators.xml
robot_retargeter/asset/robot/t800/xml/serial_links.xml
robot_retargeter/asset/robot/t800/xml/serial_sensors.xml
robot_retargeter/asset/robot/t800/xml/serial_t800.xml
robot_retargeter/asset/skeleton/mjcf/skeleton.xml
robot_retargeter/asset/skeleton/urdf/skeleton.urdf
robot_retargeter/bash/retarget_from_robot.sh
robot_retargeter/bash/retarget_from_smplx.sh
robot_retargeter/config/robot/DR02.yaml
robot_retargeter/config/robot/agibot_x2.yaml
robot_retargeter/config/robot/booster_t1.yaml
robot_retargeter/config/robot/g1.yaml
robot_retargeter/config/robot/g1_d.yaml
robot_retargeter/config/robot/h1.yaml
robot_retargeter/config/robot/h1_2.yaml
robot_retargeter/config/robot/h2.yaml
robot_retargeter/config/robot/hightorque_hi.yaml
robot_retargeter/config/robot/hightorque_pi.yaml
robot_retargeter/config/robot/jaka_pi.yaml
robot_retargeter/config/robot/kuavo.yaml
robot_retargeter/config/robot/limx_oli.yaml
robot_retargeter/config/robot/noetix_e1.yaml
robot_retargeter/config/robot/noetix_n2.yaml
robot_retargeter/config/robot/pm01.yaml
robot_retargeter/config/robot/pnd_adam.yaml
robot_retargeter/config/robot/r1.yaml
robot_retargeter/config/robot/t800.yaml
robot_retargeter/config/robot/tienkung.yaml
robot_retargeter/config/robot/unitree_a2.yaml
robot_retargeter/config/robot/unitree_a2w.yaml
robot_retargeter/config/robot/xbot.yaml
robot_retargeter/config/skeleton/skeleton.yaml
robot_retargeter/dataset/ACCAD/C17_-_run_change_direction_stageii.npz
robot_retargeter/dataset/ACCAD/Form_1_stageii.npz
robot_retargeter/dataset/bones_g1/body_check_001__A548_M.csv
robot_retargeter/dataset/bones_g1/grab_walk_ff_180_001__A550_M.csv
robot_retargeter/dataset/bones_g1_origin/body_check_001__A548_M.csv
robot_retargeter/dataset/bones_g1_origin/grab_walk_ff_180_001__A550_M.csv
robot_retargeter/dataset/lafan1_g1/Form_1_stageii_g1.csv
robot_retargeter/dataset/lafan1_g1/dance1_subject1.csv
robot_retargeter/dataset/lafan1_g1/dance1_subject2.csv
robot_retargeter/dataset/lafan1_g1/dance1_subject3.csv
robot_retargeter/dataset/lafan1_g1/dance2_subject1.csv
robot_retargeter/dataset/lafan1_g1/dance2_subject2.csv
robot_retargeter/dataset/lafan1_g1/dance2_subject3.csv
robot_retargeter/dataset/lafan1_g1/dance2_subject4.csv
robot_retargeter/dataset/lafan1_g1/dance2_subject5.csv
robot_retargeter/dataset/lafan1_g1/fallAndGetUp1_subject1.csv
robot_retargeter/dataset/lafan1_g1/fallAndGetUp1_subject4.csv
robot_retargeter/dataset/lafan1_g1/fallAndGetUp1_subject5.csv
robot_retargeter/dataset/lafan1_g1/fallAndGetUp2_subject2.csv
robot_retargeter/dataset/lafan1_g1/fallAndGetUp2_subject3.csv
robot_retargeter/dataset/lafan1_g1/fallAndGetUp3_subject1.csv
robot_retargeter/dataset/lafan1_g1/fight1_subject2.csv
robot_retargeter/dataset/lafan1_g1/fight1_subject3.csv
robot_retargeter/dataset/lafan1_g1/fight1_subject5.csv
robot_retargeter/dataset/lafan1_g1/fightAndSports1_subject1.csv
robot_retargeter/dataset/lafan1_g1/fightAndSports1_subject4.csv
robot_retargeter/dataset/lafan1_g1/jumps1_subject1.csv
robot_retargeter/dataset/lafan1_g1/jumps1_subject2.csv
robot_retargeter/dataset/lafan1_g1/jumps1_subject5.csv
robot_retargeter/dataset/lafan1_g1/run1_subject2.csv
robot_retargeter/dataset/lafan1_g1/run1_subject5.csv
robot_retargeter/dataset/lafan1_g1/run2_subject1.csv
robot_retargeter/dataset/lafan1_g1/run2_subject4.csv
robot_retargeter/dataset/lafan1_g1/sprint1_subject2.csv
robot_retargeter/dataset/lafan1_g1/sprint1_subject4.csv
robot_retargeter/dataset/lafan1_g1/walk1_subject1.csv
robot_retargeter/dataset/lafan1_g1/walk1_subject2.csv
robot_retargeter/dataset/lafan1_g1/walk1_subject5.csv
robot_retargeter/dataset/lafan1_g1/walk2_subject1.csv
robot_retargeter/dataset/lafan1_g1/walk2_subject3.csv
robot_retargeter/dataset/lafan1_g1/walk2_subject4.csv
robot_retargeter/dataset/lafan1_g1/walk3_subject1.csv
robot_retargeter/dataset/lafan1_g1/walk3_subject2.csv
robot_retargeter/dataset/lafan1_g1/walk3_subject3.csv
robot_retargeter/dataset/lafan1_g1/walk3_subject4.csv
robot_retargeter/dataset/lafan1_g1/walk3_subject5.csv
robot_retargeter/dataset/lafan1_g1/walk4_subject1.csv
robot_retargeter/requirements.txt
robot_retargeter/scripts/convert_bones_to_lafan1.py
robot_retargeter/scripts/multi_robot_visualize.py
robot_retargeter/scripts/robot_replay.py
robot_retargeter/scripts/robot_retarget.py
robot_retargeter/scripts/smpl_replay.py
robot_retargeter/setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `robot_retargeter` | 5 | 10.7 MB | [`robot_retargeter/_OMITTED.md`](./robot_retargeter/_OMITTED.md) |
| `robot_retargeter/asset/robot/DR02/mjcf/pro/meshes` | 34 | 28.5 MB | [`robot_retargeter/asset/robot/DR02/mjcf/pro/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/DR02/mjcf/pro/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/HU_D04_description/meshes/HU_D04_01` | 93 | 35.3 MB | [`robot_retargeter/asset/robot/HU_D04_description/meshes/HU_D04_01/_OMITTED.md`](./robot_retargeter/asset/robot/HU_D04_description/meshes/HU_D04_01/_OMITTED.md) |
| `robot_retargeter/asset/robot/a2_description/meshes` | 17 | 14.1 MB | [`robot_retargeter/asset/robot/a2_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/a2_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/a2w_description/meshes` | 17 | 9.6 MB | [`robot_retargeter/asset/robot/a2w_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/a2w_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/agibot_x2/meshes` | 45 | 111.1 MB | [`robot_retargeter/asset/robot/agibot_x2/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/agibot_x2/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/biped_s53` | 1 | 427 KB | [`robot_retargeter/asset/robot/biped_s53/_OMITTED.md`](./robot_retargeter/asset/robot/biped_s53/_OMITTED.md) |
| `robot_retargeter/asset/robot/biped_s53/meshes` | 79 | 53.1 MB | [`robot_retargeter/asset/robot/biped_s53/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/biped_s53/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/booster_t1/meshes` | 44 | 11.8 MB | [`robot_retargeter/asset/robot/booster_t1/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/booster_t1/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/dex_evt/meshes` | 39 | 11.3 MB | [`robot_retargeter/asset/robot/dex_evt/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/dex_evt/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/g1_d_description/meshes` | 72 | 58.2 MB | [`robot_retargeter/asset/robot/g1_d_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/g1_d_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/g1_description/meshes` | 64 | 51.8 MB | [`robot_retargeter/asset/robot/g1_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/g1_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/h1_2_description` | 1 | 753 KB | [`robot_retargeter/asset/robot/h1_2_description/_OMITTED.md`](./robot_retargeter/asset/robot/h1_2_description/_OMITTED.md) |
| `robot_retargeter/asset/robot/h1_2_description/meshes` | 150 | 77.8 MB | [`robot_retargeter/asset/robot/h1_2_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/h1_2_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/h1_description/meshes` | 98 | 80.1 MB | [`robot_retargeter/asset/robot/h1_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/h1_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/h2_description/meshes` | 69 | 41.6 MB | [`robot_retargeter/asset/robot/h2_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/h2_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/hightorque_hi/meshes` | 26 | 11.4 MB | [`robot_retargeter/asset/robot/hightorque_hi/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/hightorque_hi/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/jaka_pi/meshes` | 45 | 29.9 MB | [`robot_retargeter/asset/robot/jaka_pi/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/jaka_pi/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/l7_29dof_neck_fixed/meshes` | 109 | 22.5 MB | [`robot_retargeter/asset/robot/l7_29dof_neck_fixed/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/l7_29dof_neck_fixed/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/noetix_N2/meshes` | 21 | 69.9 MB | [`robot_retargeter/asset/robot/noetix_N2/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/noetix_N2/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/noetix_e1/meshes` | 25 | 104.8 MB | [`robot_retargeter/asset/robot/noetix_e1/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/noetix_e1/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/pi_plus_24dof/meshes` | 40 | 32.7 MB | [`robot_retargeter/asset/robot/pi_plus_24dof/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/pi_plus_24dof/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/pm01_edu/meshes` | 50 | 328.4 MB | [`robot_retargeter/asset/robot/pm01_edu/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/pm01_edu/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/pm01_edu/texture` | 23 | 47.9 MB | [`robot_retargeter/asset/robot/pm01_edu/texture/_OMITTED.md`](./robot_retargeter/asset/robot/pm01_edu/texture/_OMITTED.md) |
| `robot_retargeter/asset/robot/pnd_adam_lite` | 1 | 2.6 MB | [`robot_retargeter/asset/robot/pnd_adam_lite/_OMITTED.md`](./robot_retargeter/asset/robot/pnd_adam_lite/_OMITTED.md) |
| `robot_retargeter/asset/robot/pnd_adam_lite/assets` | 79 | 171.9 MB | [`robot_retargeter/asset/robot/pnd_adam_lite/assets/_OMITTED.md`](./robot_retargeter/asset/robot/pnd_adam_lite/assets/_OMITTED.md) |
| `robot_retargeter/asset/robot/pnd_adam_lite/meshes` | 35 | 93.7 MB | [`robot_retargeter/asset/robot/pnd_adam_lite/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/pnd_adam_lite/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/r1_description/meshes` | 43 | 21.6 MB | [`robot_retargeter/asset/robot/r1_description/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/r1_description/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/t800/meshes` | 52 | 84.9 MB | [`robot_retargeter/asset/robot/t800/meshes/_OMITTED.md`](./robot_retargeter/asset/robot/t800/meshes/_OMITTED.md) |
| `robot_retargeter/asset/robot/t800/texture` | 16 | 28.2 MB | [`robot_retargeter/asset/robot/t800/texture/_OMITTED.md`](./robot_retargeter/asset/robot/t800/texture/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
