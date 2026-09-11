# microduck_all — 参考资源

> **来源**：`00_open/microduck_all/`　｜　**类型**：参考项目
> **关联机型**：microduck（MicroDuck 双足）
> **定位**：MicroDuck 综合工程
> **收录**：982 个文件 / 64.6 MB（其中推理策略/模型文件 55 个）
> **已省略**：832 个文件 / 310.2 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（188 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（39 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（70 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（85 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（9 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（4 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（55 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（532 个）：文档、说明、许可与零散脚本

## 目录构成

```text
318_lab-microduck-simulator/  （59 个文件）
    (直接文件)/
    .github/
    app/
    training/
microduck/  （279 个文件）
    (直接文件)/
    .cargo/
    .github/
    btd/
    configd/
    deploy/
    docs/
    duck-control/
    duck-detect/
    duck-ipc-proto/
    duckctl/
    hooks/
    kinematics/
    mediad/
    odometry/
    padd/
    pet-detect/
    policies/
    robotctl/
    robotd/
    …（其余 7 个子目录）
microduck-3d/  （8 个文件）
    (直接文件)/
microduck-gst-plugins/  （9 个文件）
    (直接文件)/
    .github/
    patches/
    scripts/
microduck-mcp/  （18 个文件）
    (直接文件)/
    docs/
    machines/
    src/
    tests/
microduck-miniverse/  （21 个文件）
    (直接文件)/
    checkpoints/
    scripts/
microduck-sandbox/  （57 个文件）
    (直接文件)/
    app/
microduck-simulator/  （55 个文件）
    (直接文件)/
    app/
microduck_app/  （35 个文件）
    (直接文件)/
    .github/
    deploy/
    public/
    robot_assets/
    scripts/
    src/
microduck_kinematics_rs/  （16 个文件）
    (直接文件)/
    assets/
    scripts/
    src/
    tests/
microduck_maploc_rs/  （36 个文件）
    (直接文件)/
    docs/
    examples/
    sessions/
    src/
    tools/
microduck_pet_detect/  （12 个文件）
    (直接文件)/
    .github/
    models/
    src/
    training/
microduck_rl/  （165 个文件）
    (直接文件)/
    docs/
    scripts/
    src/
    tests/
microduck_runtime/  （32 个文件）
    (直接文件)/
    .github/
    policies/
    rpi_setup/
    src/
microduck_sounds/  （10 个文件）
    (直接文件)/
    microduck_sounds/
micropal/  （24 个文件）
    (直接文件)/
    .github/
    Scripts/
    Sources/
    Support/
mjlab_microduck_waddle/  （146 个文件）
    (直接文件)/
    scripts/
    src/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.rs` | 179 |
| `.part` | 156 |
| `.py` | 112 |
| `.md` | 79 |
| `.js` | 66 |
| `.onnx` | 54 |
| `.xml` | 50 |
| `(无扩展名)` | 41 |
| `.toml` | 39 |
| `.json` | 37 |
| `.jsx` | 33 |
| `.sh` | 24 |
| `.swift` | 17 |
| `.yml` | 13 |
| `.html` | 11 |

## 文件索引（项目内相对路径）

```text
318_lab-microduck-simulator/.github/workflows/deploy.yml
318_lab-microduck-simulator/.gitignore
318_lab-microduck-simulator/Dockerfile
318_lab-microduck-simulator/README.md
318_lab-microduck-simulator/app/.gitignore
318_lab-microduck-simulator/app/index.html
318_lab-microduck-simulator/app/package-lock.json
318_lab-microduck-simulator/app/package.json
318_lab-microduck-simulator/app/public/policies/BEST_alpha_sitstand.onnx
318_lab-microduck-simulator/app/public/policies/BEST_alpha_stand.onnx
318_lab-microduck-simulator/app/public/policies/BEST_alpha_walking.onnx
318_lab-microduck-simulator/app/public/policies/BEST_roller.onnx
318_lab-microduck-simulator/app/public/policies/BEST_roller_crouch.onnx
318_lab-microduck-simulator/app/public/policies/alpha_ground_pick.onnx
318_lab-microduck-simulator/app/public/policies/ball_kick_left.onnx
318_lab-microduck-simulator/app/public/policies/ball_kick_right.onnx
318_lab-microduck-simulator/app/public/policies/jump.onnx
318_lab-microduck-simulator/app/public/policies/roulade.onnx
318_lab-microduck-simulator/app/public/robot/mjlab/kinematics.json
318_lab-microduck-simulator/app/public/robot/mjlab/kinematics_rollers.json
318_lab-microduck-simulator/app/public/robot/mjlab/robot_allcollisions.xml
318_lab-microduck-simulator/app/public/robot/mjlab/robot_allcollisions_rollers.xml
318_lab-microduck-simulator/app/src/App.jsx
318_lab-microduck-simulator/app/src/game/arena.js
318_lab-microduck-simulator/app/src/game/ball-actor.js
318_lab-microduck-simulator/app/src/game/ball-visual.js
318_lab-microduck-simulator/app/src/game/ceremony.js
318_lab-microduck-simulator/app/src/game/constants.js
318_lab-microduck-simulator/app/src/game/controls/controller.js
318_lab-microduck-simulator/app/src/game/controls/gamepad.js
318_lab-microduck-simulator/app/src/game/controls/keyboard.js
318_lab-microduck-simulator/app/src/game/controls/touch.js
318_lab-microduck-simulator/app/src/game/duck.js
318_lab-microduck-simulator/app/src/game/fx/demo-glitch.html
318_lab-microduck-simulator/app/src/game/fx/demo-wireframe.html
318_lab-microduck-simulator/app/src/game/fx/fx-glitch.js
318_lab-microduck-simulator/app/src/game/fx/fx-wireframe.js
318_lab-microduck-simulator/app/src/game/game.js
318_lab-microduck-simulator/app/src/game/ghosts.js
318_lab-microduck-simulator/app/src/game/props.js
318_lab-microduck-simulator/app/src/game/signed.js
318_lab-microduck-simulator/app/src/game/stickers.js
318_lab-microduck-simulator/app/src/game/variants.js
318_lab-microduck-simulator/app/src/main.jsx
318_lab-microduck-simulator/app/src/scene/CrtDistortion.jsx
318_lab-microduck-simulator/app/src/scene/GameCanvas.jsx
318_lab-microduck-simulator/app/src/store.js
318_lab-microduck-simulator/app/src/theme.js
318_lab-microduck-simulator/app/src/ui/BiosOverlay.jsx
318_lab-microduck-simulator/app/src/ui/Hud.jsx
318_lab-microduck-simulator/app/src/ui/Overlays.jsx
318_lab-microduck-simulator/app/src/ui/Preboot.jsx
318_lab-microduck-simulator/app/src/ui/TitleMenu.jsx
318_lab-microduck-simulator/app/src/ui/TouchOverlay.jsx
318_lab-microduck-simulator/app/src/ui/comic.jsx
318_lab-microduck-simulator/app/vite.config.js
318_lab-microduck-simulator/training/README.md
318_lab-microduck-simulator/training/mdp_with_jump.py
318_lab-microduck-simulator/training/microduck_jump_env_cfg.py
microduck-3d/README.md
microduck-3d/assemble.py
microduck-3d/kinematics.json
microduck-3d/kinematics_rollers.json
microduck-3d/microduck_combined.xml
microduck-3d/microduck_combined_rollers.xml
microduck-3d/robot_allcollisions.xml
microduck-3d/robot_allcollisions_rollers.xml
microduck-gst-plugins/.github/workflows/release.yml
microduck-gst-plugins/.gitignore
microduck-gst-plugins/LICENSE
microduck-gst-plugins/README.md
microduck-gst-plugins/patches/README.md
microduck-gst-plugins/patches/gst-plugins-rs/0001-webrtcsink-no-converter-for-mpph264enc.patch
microduck-gst-plugins/patches/gstreamer-rockchip/0001-mpph264enc-advertise-constrained-baseline.patch
microduck-gst-plugins/pins.env
microduck-gst-plugins/scripts/build.sh
microduck-mcp/.gitignore
microduck-mcp/LICENSE
microduck-mcp/README.md
microduck-mcp/docs/mcp-design-notes.md
microduck-mcp/machines/soccer.toml
microduck-mcp/machines/striker.toml
microduck-mcp/pyproject.toml
microduck-mcp/src/microduck_mcp/__init__.py
microduck-mcp/src/microduck_mcp/client.py
microduck-mcp/src/microduck_mcp/machine.py
microduck-mcp/src/microduck_mcp/mcp_server.py
microduck-mcp/src/microduck_mcp/sim_server.py
microduck-mcp/src/microduck_mcp/webui.py
microduck-mcp/tests/live/test_live_sim.py
microduck-mcp/tests/test_ball_seen.py
microduck-mcp/tests/test_goal.py
microduck-mcp/tests/test_goal_seen.py
microduck-mcp/tests/test_machine.py
microduck-miniverse/.gitattributes
microduck-miniverse/.gitignore
microduck-miniverse/LICENSE
microduck-miniverse/README.md
microduck-miniverse/SHA256SUMS
microduck-miniverse/SPEC.md
microduck-miniverse/THIRD_PARTY_NOTICES.md
microduck-miniverse/checkpoints/BEST_alpha_sitstand.onnx
microduck-miniverse/checkpoints/BEST_alpha_stand.onnx
microduck-miniverse/checkpoints/BEST_alpha_walking.onnx
microduck-miniverse/checkpoints/BEST_roller.onnx
microduck-miniverse/checkpoints/BEST_roller_crouch.onnx
microduck-miniverse/checkpoints/alpha_ground_pick.onnx
microduck-miniverse/checkpoints/ball_kick_left.onnx
microduck-miniverse/checkpoints/ball_kick_right.onnx
microduck-miniverse/checkpoints/roulade.onnx
microduck-miniverse/policies.json
microduck-miniverse/policy.py
microduck-miniverse/pyproject.toml
microduck-miniverse/scripts/build.py
microduck-miniverse/scripts/publish.py
microduck-sandbox/.gitattributes
microduck-sandbox/.gitignore
microduck-sandbox/Dockerfile
microduck-sandbox/LICENSE
microduck-sandbox/README.md
microduck-sandbox/app/.gitignore
microduck-sandbox/app/index.html
microduck-sandbox/app/package-lock.json
microduck-sandbox/app/package.json
microduck-sandbox/app/public/policies/BEST_alpha_sitstand.onnx
microduck-sandbox/app/public/policies/BEST_alpha_stand.onnx
microduck-sandbox/app/public/policies/BEST_alpha_walking.onnx
microduck-sandbox/app/public/policies/BEST_roller.onnx
microduck-sandbox/app/public/policies/BEST_roller_crouch.onnx
microduck-sandbox/app/public/policies/alpha_ground_pick.onnx
microduck-sandbox/app/public/policies/ball_kick_left.onnx
microduck-sandbox/app/public/policies/ball_kick_right.onnx
microduck-sandbox/app/public/policies/roulade.onnx
microduck-sandbox/app/public/robot/mjlab/kinematics.json
microduck-sandbox/app/public/robot/mjlab/kinematics_rollers.json
microduck-sandbox/app/public/robot/mjlab/robot_allcollisions.xml
microduck-sandbox/app/public/robot/mjlab/robot_allcollisions_rollers.xml
microduck-sandbox/app/src/App.jsx
microduck-sandbox/app/src/game/arena.js
microduck-sandbox/app/src/game/ball-actor.js
microduck-sandbox/app/src/game/ball-visual.js
microduck-sandbox/app/src/game/band.js
microduck-sandbox/app/src/game/ceremony.js
microduck-sandbox/app/src/game/constants.js
microduck-sandbox/app/src/game/controls/controller.js
microduck-sandbox/app/src/game/controls/gamepad.js
microduck-sandbox/app/src/game/controls/keyboard.js
microduck-sandbox/app/src/game/controls/touch.js
microduck-sandbox/app/src/game/duck.js
microduck-sandbox/app/src/game/fx/demo-glitch.html
microduck-sandbox/app/src/game/fx/demo-wireframe.html
microduck-sandbox/app/src/game/fx/fx-glitch.js
microduck-sandbox/app/src/game/fx/fx-wireframe.js
microduck-sandbox/app/src/game/game.js
microduck-sandbox/app/src/game/ghosts.js
microduck-sandbox/app/src/game/props.js
microduck-sandbox/app/src/game/signed.js
microduck-sandbox/app/src/game/stickers.js
microduck-sandbox/app/src/game/variants.js
microduck-sandbox/app/src/main.jsx
microduck-sandbox/app/src/scene/CrtDistortion.jsx
microduck-sandbox/app/src/scene/GameCanvas.jsx
microduck-sandbox/app/src/store.js
microduck-sandbox/app/src/theme.js
microduck-sandbox/app/src/ui/BiosOverlay.jsx
microduck-sandbox/app/src/ui/Hud.jsx
microduck-sandbox/app/src/ui/Overlays.jsx
microduck-sandbox/app/src/ui/Preboot.jsx
microduck-sandbox/app/src/ui/TitleMenu.jsx
microduck-sandbox/app/src/ui/TouchOverlay.jsx
microduck-sandbox/app/src/ui/comic.jsx
microduck-sandbox/app/vite.config.js
microduck-simulator/.gitattributes
microduck-simulator/.gitignore
microduck-simulator/Dockerfile
microduck-simulator/README.md
microduck-simulator/app/.gitignore
microduck-simulator/app/index.html
microduck-simulator/app/package-lock.json
microduck-simulator/app/package.json
microduck-simulator/app/public/policies/BEST_alpha_sitstand.onnx
microduck-simulator/app/public/policies/BEST_alpha_stand.onnx
microduck-simulator/app/public/policies/BEST_alpha_walking.onnx
microduck-simulator/app/public/policies/BEST_roller.onnx
microduck-simulator/app/public/policies/BEST_roller_crouch.onnx
microduck-simulator/app/public/policies/alpha_ground_pick.onnx
microduck-simulator/app/public/policies/ball_kick_left.onnx
microduck-simulator/app/public/policies/ball_kick_right.onnx
microduck-simulator/app/public/policies/roulade.onnx
microduck-simulator/app/public/robot/mjlab/kinematics.json
microduck-simulator/app/public/robot/mjlab/kinematics_rollers.json
microduck-simulator/app/public/robot/mjlab/robot_allcollisions.xml
microduck-simulator/app/public/robot/mjlab/robot_allcollisions_rollers.xml
microduck-simulator/app/src/App.jsx
microduck-simulator/app/src/game/arena.js
microduck-simulator/app/src/game/ball-actor.js
microduck-simulator/app/src/game/ball-visual.js
microduck-simulator/app/src/game/ceremony.js
microduck-simulator/app/src/game/constants.js
microduck-simulator/app/src/game/controls/controller.js
microduck-simulator/app/src/game/controls/gamepad.js
microduck-simulator/app/src/game/controls/keyboard.js
microduck-simulator/app/src/game/controls/touch.js
microduck-simulator/app/src/game/duck.js
microduck-simulator/app/src/game/fx/demo-glitch.html
microduck-simulator/app/src/game/fx/demo-wireframe.html
microduck-simulator/app/src/game/fx/fx-glitch.js
microduck-simulator/app/src/game/fx/fx-wireframe.js
microduck-simulator/app/src/game/game.js
microduck-simulator/app/src/game/ghosts.js
microduck-simulator/app/src/game/props.js
microduck-simulator/app/src/game/signed.js
microduck-simulator/app/src/game/stickers.js
microduck-simulator/app/src/game/variants.js
microduck-simulator/app/src/main.jsx
microduck-simulator/app/src/scene/CrtDistortion.jsx
microduck-simulator/app/src/scene/GameCanvas.jsx
microduck-simulator/app/src/store.js
microduck-simulator/app/src/theme.js
microduck-simulator/app/src/ui/BiosOverlay.jsx
microduck-simulator/app/src/ui/Hud.jsx
microduck-simulator/app/src/ui/Overlays.jsx
microduck-simulator/app/src/ui/Preboot.jsx
microduck-simulator/app/src/ui/TitleMenu.jsx
microduck-simulator/app/src/ui/TouchOverlay.jsx
microduck-simulator/app/src/ui/comic.jsx
microduck-simulator/app/vite.config.js
microduck/.cargo/config.toml
microduck/.github/workflows/_build-release.yml
microduck/.github/workflows/_promote-release.yml
microduck/.github/workflows/ci.yml
microduck/.github/workflows/dev.yml
microduck/.github/workflows/promote.yml
microduck/.github/workflows/prune-dev-releases.yml
microduck/.github/workflows/release.yml
microduck/.gitignore
microduck/CONTRIBUTING.md
microduck/Cargo.toml
microduck/LICENSE
microduck/README.md
microduck/btd/Cargo.toml
microduck/btd/src/adv.rs
microduck/btd/src/bluez.rs
microduck/btd/src/chorale.rs
microduck/btd/src/framing.rs
microduck/btd/src/gatt.rs
microduck/btd/src/lib.rs
microduck/btd/src/link.rs
microduck/btd/src/main.rs
microduck/btd/src/pairing.rs
microduck/btd/src/route.rs
microduck/btd/src/session.rs
microduck/btd/src/upstream.rs
microduck/btd/systemd/btd.service
microduck/btd/systemd/sysusers.d/btd.conf
microduck/configd/Cargo.toml
microduck/configd/src/bluez.rs
microduck/configd/src/identity.rs
microduck/configd/src/lib.rs
microduck/configd/src/main.rs
microduck/configd/src/net.rs
microduck/configd/src/nm.rs
microduck/configd/src/pad.rs
microduck/configd/src/power.rs
microduck/configd/src/store.rs
microduck/configd/src/units.rs
microduck/configd/systemd/configd.service
microduck/configd/systemd/sysusers.d/README
microduck/deploy/README.md
microduck/deploy/audio/aic3104-i2c3.dts
microduck/deploy/audio/aic3104-init.sh
microduck/deploy/audio/aic3x-dkms/Makefile
microduck/deploy/audio/aic3x-dkms/dkms.conf
microduck/deploy/audio/aic3x-dkms/tlv320aic3x-i2c.c
microduck/deploy/audio/aic3x-dkms/tlv320aic3x.c
microduck/deploy/audio/aic3x-dkms/tlv320aic3x.h
microduck/deploy/audio/i2c3-pihat.dts
microduck/deploy/dev-key/README.md
microduck/deploy/dev-key/team.dev.pub
microduck/deploy/journald.conf.d/10-robot.conf
microduck/deploy/overlays/rk3568-npu-enable.dts
microduck/deploy/robotd.toml
microduck/deploy/trusted_keys/README.md
microduck/deploy/trusted_keys/release-1.pub
microduck/deploy/trusted_keys/release-2.pub
microduck/deploy/trusted_keys/release-3.pub
microduck/deploy/updater.toml
microduck/docs/README.md
microduck/docs/design/app-path-design.md
microduck/docs/design/architecture.md
microduck/docs/design/boot-recovery-net.md
microduck/docs/design/remote-webrtc.md
microduck/docs/design/restart-order.md
microduck/docs/design/robotd-design.md
microduck/docs/design/updater-design.md
microduck/docs/design/webrtc-console.md
microduck/docs/ideas/autonomous_behavior.md
microduck/docs/project/ci-setup.md
microduck/docs/project/install-path-gap.md
microduck/docs/project/media-bringup.md
microduck/docs/project/npu-bringup.md
microduck/docs/project/pad-minimal-pairing.md
microduck/docs/project/roadmap.md
microduck/docs/project/slice-2-bringup.md
microduck/docs/project/update-over-ble.md
microduck/docs/robot/cheatsheet-dev.md
microduck/docs/robot/cheatsheet.md
microduck/docs/robot/dev-push.md
microduck/docs/robot/duckctl.md
microduck/docs/robot/install-by-hand.md
microduck/docs/robot/install-dev.md
microduck/docs/robot/pair-a-gamepad.md
microduck/duck-control/Cargo.toml
microduck/duck-control/src/bus.rs
microduck/duck-control/src/fall.rs
microduck/duck-control/src/imu.rs
microduck/duck-control/src/io.rs
microduck/duck-control/src/lib.rs
microduck/duck-control/src/model.rs
microduck/duck-control/src/obs.rs
microduck/duck-control/src/policy.rs
microduck/duck-control/src/safety.rs
microduck/duck-detect/Cargo.toml
microduck/duck-detect/models/duck_detect.onnx
microduck/duck-detect/models/duck_detect.rknn
microduck/duck-detect/src/bin/duck-bench.rs
microduck/duck-detect/src/lib.rs
microduck/duck-detect/src/onnx.rs
microduck/duck-detect/src/rknn.rs
microduck/duck-ipc-proto/Cargo.toml
microduck/duck-ipc-proto/src/lib.rs
microduck/duckctl/Cargo.toml
microduck/duckctl/examples/advwatch.rs
microduck/duckctl/src/main.rs
microduck/hooks/postinstall
microduck/hooks/preinstall.in
microduck/kinematics/Cargo.toml
microduck/kinematics/assets/alpha/robot_walk.xml
microduck/kinematics/src/hand.rs
microduck/kinematics/src/head.rs
microduck/kinematics/src/lib.rs
microduck/kinematics/src/math.rs
microduck/kinematics/src/mjcf.rs
microduck/kinematics/src/tof.rs
microduck/kinematics/tests/fixtures/fk_alpha.json
microduck/kinematics/tests/fk_against_mujoco.rs
microduck/kinematics/tests/perf_probe.rs
microduck/mediad/Cargo.toml
microduck/mediad/src/config.rs
microduck/mediad/src/detect.rs
microduck/mediad/src/exposure.rs
microduck/mediad/src/lib.rs
microduck/mediad/src/main.rs
microduck/mediad/src/pipeline.rs
microduck/mediad/src/producer.rs
microduck/mediad/src/route.rs
microduck/mediad/src/session.rs
microduck/mediad/src/upstream.rs
microduck/mediad/src/web.rs
microduck/mediad/systemd/mediad.service
microduck/mediad/systemd/sysusers.d/mediad.conf
microduck/mediad/webclient/index.html
microduck/odometry/Cargo.toml
microduck/odometry/src/lib.rs
microduck/padd/Cargo.toml
microduck/padd/src/main.rs
microduck/padd/src/tap.rs
microduck/padd/systemd/padd.service
microduck/padd/systemd/sysusers.d/padd.conf
microduck/pet-detect/Cargo.toml
microduck/pet-detect/README.md
microduck/pet-detect/models/pet_detect.onnx
microduck/pet-detect/src/bin/detect.rs
microduck/pet-detect/src/bin/features.rs
microduck/pet-detect/src/lib.rs
microduck/pet-detect/src/worker.rs
microduck/pet-detect/training/train.py
microduck/policies/README.md
microduck/policies/alpha_ground_pick.onnx
microduck/policies/alpha_sitstand.onnx
microduck/policies/alpha_stand.onnx
microduck/policies/alpha_walking.onnx
microduck/policies/ball_kick_left.onnx
microduck/policies/ball_kick_right.onnx
microduck/policies/roller.onnx
microduck/policies/roller_crouch.onnx
microduck/policies/roulade.onnx
microduck/robotctl/Cargo.toml
microduck/robotctl/src/configure.rs
microduck/robotctl/src/duck.rs
microduck/robotctl/src/main.rs
microduck/robotctl/src/monitor.rs
microduck/robotctl/src/path_map.rs
microduck/robotctl/src/show.rs
microduck/robotd-params/Cargo.toml
microduck/robotd-params/src/lib.rs
microduck/robotd-params/src/registry.rs
microduck/robotd/Cargo.toml
microduck/robotd/src/chorale.rs
microduck/robotd/src/control.rs
microduck/robotd/src/intents.rs
microduck/robotd/src/main.rs
microduck/robotd/src/params.rs
microduck/robotd/src/soc.rs
microduck/robotd/src/sound.rs
microduck/robotd/src/theremin.rs
microduck/robotd/systemd/robotd.service
microduck/robotd/tests/updater_gate.rs
microduck/scripts/bake-duck-mesh.py
microduck/scripts/board-test.sh
microduck/scripts/ci-release-notes.sh
microduck/scripts/cross-sysroot.sh
microduck/scripts/dev-build.Dockerfile
microduck/scripts/dev-push.sh
microduck/scripts/install.sh
microduck/scripts/migrate-network.sh
microduck/scripts/pad-link-test.sh
microduck/scripts/pad-stack-report.sh
microduck/scripts/provision-board.sh
microduck/scripts/provision.sh
microduck/scripts/rkaiq-modinfo-shim.c
microduck/scripts/robot-boot-check
microduck/scripts/robot-rescue
microduck/scripts/setup-board.sh
microduck/scripts/setup-gstreamer.sh
microduck/scripts/setup-login.sh
microduck/scripts/setup-npu.sh
microduck/scripts/setup-rkaiq.sh
microduck/scripts/systemd-test.Dockerfile
microduck/scripts/systemd-test.sh
microduck/sounds/Cargo.toml
microduck/sounds/scores/wistful.duckscore
microduck/sounds/src/chorale/beat.rs
microduck/sounds/src/chorale/midi.rs
microduck/sounds/src/chorale/mod.rs
microduck/sounds/src/chorale/text.rs
microduck/sounds/src/lib.rs
microduck/sounds/src/main.rs
microduck/sounds/src/personality.rs
microduck/sounds/src/rng.rs
microduck/sounds/src/stream.rs
microduck/sounds/src/synth.rs
microduck/sounds/src/voices.rs
microduck/test-support/Cargo.toml
microduck/test-support/examples/fake-release.rs
microduck/test-support/examples/systemd-fixture.rs
microduck/test-support/src/lib.rs
microduck/tof/Cargo.toml
microduck/tof/build.rs
microduck/tof/src/lib.rs
microduck/tof/src/main.rs
microduck/tof/src/sensor.rs
microduck/tof/src/status.rs
microduck/tof/systemd/sysusers.d/tofd.conf
microduck/tof/systemd/tofd.service
microduck/tof/vendor/LICENSE.txt
microduck/tof/vendor/platform.c
microduck/tof/vendor/probe.c
microduck/tof/vendor/vl53l5cx/platform.h
microduck/tof/vendor/vl53l5cx/shim.c
microduck/tof/vendor/vl53l5cx/vl53l5cx_api.c
microduck/tof/vendor/vl53l5cx/vl53l5cx_api.h
microduck/tof/vendor/vl53l5cx/vl53l5cx_buffers.h
microduck/tof/vendor/vl53l8cx/platform.h
microduck/tof/vendor/vl53l8cx/shim.c
microduck/tof/vendor/vl53l8cx/vl53l8cx_api.c
microduck/tof/vendor/vl53l8cx/vl53l8cx_api.h
microduck/tof/vendor/vl53l8cx/vl53l8cx_buffers.h
microduck/updater/Cargo.toml
microduck/updater/src/config.rs
microduck/updater/src/engine.rs
microduck/updater/src/faults.rs
microduck/updater/src/fsutil.rs
microduck/updater/src/hooks.rs
microduck/updater/src/ipc.rs
microduck/updater/src/journal.rs
microduck/updater/src/lib.rs
microduck/updater/src/main.rs
microduck/updater/src/manifest.rs
microduck/updater/src/orphan.rs
microduck/updater/src/preflight.rs
microduck/updater/src/reconcile.rs
microduck/updater/src/robot.rs
microduck/updater/src/source/github.rs
microduck/updater/src/source/hf_hub.rs
microduck/updater/src/source/http.rs
microduck/updater/src/source/local.rs
microduck/updater/src/source/mod.rs
microduck/updater/src/spawn.rs
microduck/updater/src/store.rs
microduck/updater/src/transcript.rs
microduck/updater/src/verify.rs
microduck/updater/systemd/robot-boot-check.service
microduck/updater/systemd/robot-boot-check.timer
microduck/updater/systemd/sysusers.d/robot.conf
microduck/updater/systemd/updaterd.service
microduck/updater/tests/apply.rs
microduck/updater/tests/download.rs
microduck/updater/tests/install.rs
microduck/updater/tests/ipc.rs
microduck/updater/updater.example.toml
microduck/xtask/Cargo.toml
microduck/xtask/src/main.rs
microduck/xtask/tests/artifact.rs
microduck/xtask/tests/rescue.rs
microduck/xtask/tests/sideload.rs
microduck_app/.github/workflows/release.yml
microduck_app/.gitignore
microduck_app/README.md
microduck_app/aze
microduck_app/deploy/microduck-app.service
microduck_app/deploy/serve.py
microduck_app/index.html
microduck_app/install.sh
microduck_app/package-lock.json
microduck_app/package.json
microduck_app/postcss.config.js
microduck_app/public/robot/alpha/kinematics.json
microduck_app/public/robot/v1.5/kinematics.json
microduck_app/public/robot/v1/kinematics.json
microduck_app/robot_assets/alpha/robot_walk.xml
microduck_app/robot_assets/v1.5/robot_walk.xml
microduck_app/robot_assets/v1/robot_walk.xml
microduck_app/scripts/build_kinematics.py
microduck_app/src/App.tsx
microduck_app/src/components/BatteryPill.tsx
microduck_app/src/components/BrainHUD.tsx
microduck_app/src/components/CameraView.tsx
microduck_app/src/components/DuckViewer.tsx
microduck_app/src/components/MapView.tsx
microduck_app/src/components/SettingsSheet.tsx
microduck_app/src/components/StatusPill.tsx
microduck_app/src/duck/kinematics.ts
microduck_app/src/main.tsx
microduck_app/src/state/connection.ts
microduck_app/src/state/telemetry.ts
microduck_app/src/styles.css
microduck_app/tailwind.config.js
microduck_app/tsconfig.json
microduck_app/tsconfig.tsbuildinfo
microduck_app/vite.config.ts
microduck_kinematics_rs/.gitignore
microduck_kinematics_rs/Cargo.toml
microduck_kinematics_rs/README.md
microduck_kinematics_rs/assets/alpha/robot_walk.xml
microduck_kinematics_rs/assets/v1.5/robot_walk.xml
microduck_kinematics_rs/assets/v1/robot_walk.xml
microduck_kinematics_rs/scripts/gen_fixtures.py
microduck_kinematics_rs/scripts/pyproject.toml
microduck_kinematics_rs/scripts/strip_mjcf.py
microduck_kinematics_rs/src/lib.rs
microduck_kinematics_rs/src/mjcf.rs
microduck_kinematics_rs/src/model.rs
microduck_kinematics_rs/tests/fixtures/fk_alpha.json
microduck_kinematics_rs/tests/fixtures/fk_v1.5.json
microduck_kinematics_rs/tests/fixtures/fk_v1.json
microduck_kinematics_rs/tests/fk_against_mujoco.rs
microduck_maploc_rs/.gitignore
microduck_maploc_rs/Cargo.toml
microduck_maploc_rs/README.md
microduck_maploc_rs/docs/DESIGN.md
microduck_maploc_rs/docs/PLAN.md
microduck_maploc_rs/examples/bench_field.rs
microduck_maploc_rs/examples/dump_session.rs
microduck_maploc_rs/examples/live_track.rs
microduck_maploc_rs/examples/track_loop_closure.rs
microduck_maploc_rs/examples/track_session.rs
microduck_maploc_rs/examples/track_submaps.rs
microduck_maploc_rs/pyproject.toml
microduck_maploc_rs/sessions/test_room_loop1.mdlg
microduck_maploc_rs/src/follower.rs
microduck_maploc_rs/src/global_render.rs
microduck_maploc_rs/src/grid.rs
microduck_maploc_rs/src/lib.rs
microduck_maploc_rs/src/loop_closer.rs
microduck_maploc_rs/src/mcl.rs
microduck_maploc_rs/src/mount.rs
microduck_maploc_rs/src/optimizer.rs
microduck_maploc_rs/src/planner.rs
microduck_maploc_rs/src/pose_graph.rs
microduck_maploc_rs/src/relocalize.rs
microduck_maploc_rs/src/replay.rs
microduck_maploc_rs/src/scan_matcher.rs
microduck_maploc_rs/src/session.rs
microduck_maploc_rs/src/stream.rs
microduck_maploc_rs/src/submap.rs
microduck_maploc_rs/src/submap_manager.rs
microduck_maploc_rs/src/wire.rs
microduck_maploc_rs/tools/calibrate_tof.py
microduck_maploc_rs/tools/live_view.py
microduck_maploc_rs/tools/record_session.py
microduck_maploc_rs/tools/repair_mdlg_172to180.py
microduck_maploc_rs/tools/replay_session.py
microduck_pet_detect/.github/workflows/release.yml
microduck_pet_detect/.gitignore
microduck_pet_detect/Cargo.toml
microduck_pet_detect/Cross.toml
microduck_pet_detect/README.md
microduck_pet_detect/install.sh
microduck_pet_detect/models/pet_detect.onnx
microduck_pet_detect/models/pet_detect_v0.onnx
microduck_pet_detect/src/bin/detect.rs
microduck_pet_detect/src/bin/features.rs
microduck_pet_detect/src/lib.rs
microduck_pet_detect/training/train.py
microduck_rl/.gitignore
microduck_rl/AGENTS.md
microduck_rl/CLAUDE.md
microduck_rl/LICENSE
microduck_rl/README.md
microduck_rl/docs/roller_standup_policy_summary.md
microduck_rl/docs/superpowers/plans/2026-07-17-roller-crouch-glide.md
microduck_rl/docs/superpowers/plans/2026-07-22-roller-slope.md
microduck_rl/docs/superpowers/plans/2026-07-24-ground-pick-pose-following.md
microduck_rl/docs/superpowers/plans/2026-07-24-shoot-pose-following.md
microduck_rl/docs/superpowers/plans/2026-07-27-swizzle-head-control.md
microduck_rl/docs/superpowers/plans/2026-08-04-roller-standup.md
microduck_rl/docs/superpowers/plans/2026-08-04-spin-env.md
microduck_rl/docs/superpowers/specs/2026-07-17-roller-crouch-glide-design.md
microduck_rl/docs/superpowers/specs/2026-07-22-roller-slope-design.md
microduck_rl/docs/superpowers/specs/2026-07-23-swizzle-env-design.md
microduck_rl/docs/superpowers/specs/2026-07-24-ground-pick-pose-following-design.md
microduck_rl/docs/superpowers/specs/2026-07-24-shoot-pose-following-design.md
microduck_rl/docs/superpowers/specs/2026-07-27-swizzle-head-control-design.md
microduck_rl/docs/superpowers/specs/2026-08-04-roller-standup-design.md
microduck_rl/docs/superpowers/specs/2026-08-04-spin-env-design.md
microduck_rl/pyproject.toml
microduck_rl/scripts/crouch_pose_editor.py
microduck_rl/scripts/export.py
microduck_rl/scripts/hf/README.md
microduck_rl/scripts/hf/train_hf.py
microduck_rl/scripts/hf/uploader.py
microduck_rl/scripts/infer_policy.py
microduck_rl/scripts/play_latest.py
microduck_rl/scripts/plot_observations_comparison_plotly.py
microduck_rl/scripts/testbench_sim2real.py
microduck_rl/scripts/validate_bam_testbench.py
microduck_rl/scripts/view_slope_terrain.py
microduck_rl/scripts/wandb_utils.py
microduck_rl/src/mjlab_microduck/__init__.py
microduck_rl/src/mjlab_microduck/actuator/__init__.py
microduck_rl/src/mjlab_microduck/actuator/friction_dr_bam.py
microduck_rl/src/mjlab_microduck/hf_jobs.py
microduck_rl/src/mjlab_microduck/robot/__init__.py
microduck_rl/src/mjlab_microduck/robot/microduck/add_backlash.py
microduck_rl/src/mjlab_microduck/robot/microduck/additional.xml
microduck_rl/src/mjlab_microduck/robot/microduck/assets/ankle_l_v1.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/ankle_left.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/ankle_r_v1.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/ankle_right.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/banana_pcb_locker.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/bearing_roll.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/bottom_head_shell.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/elec_rpi_robot_hat_pcb.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/face_part.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/foot_left.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/foot_right.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/hip_l.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/jaw.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/jaw_soft.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/left_shell.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/left_upper_leg.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/leg.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/lens.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/m12_lens_holder.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/motor_support.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/neck.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/neck_pitch.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/noenoeil.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/np_f970.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/pcb__raspberry_pi_zero_2_w.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/power_support.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/right_shell.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/right_upper_leg.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/rim.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/roller_blade.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/seeed_bearing__configuration__22x16x4.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/seeed_bearing__configuration_default.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/soft_mouth_top.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/sole_left.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/sole_right.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/speaker.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/tire.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/top_head_shell.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/trunk_base.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/trunk_shell_left.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/trunk_shell_right.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/upper_leg_left.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/upper_leg_right.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/upper_leg_rigidity_plate.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/xl330.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/yaw2roll.part
microduck_rl/src/mjlab_microduck/robot/microduck/assets/yaw_roll_motion.part
microduck_rl/src/mjlab_microduck/robot/microduck/ball.xml
microduck_rl/src/mjlab_microduck/robot/microduck/config_mjcf_allcollisions.json
microduck_rl/src/mjlab_microduck/robot/microduck/config_mjcf_allcollisions_backlash.json
microduck_rl/src/mjlab_microduck/robot/microduck/config_mjcf_allcollisions_rollers.json
microduck_rl/src/mjlab_microduck/robot/microduck/config_mjcf_allcollisions_rollers_backlash.json
microduck_rl/src/mjlab_microduck/robot/microduck/config_mjcf_walk.json
microduck_rl/src/mjlab_microduck/robot/microduck/config_mjcf_walk_backlash.json
microduck_rl/src/mjlab_microduck/robot/microduck/joints_properties.xml
microduck_rl/src/mjlab_microduck/robot/microduck/microduck.urdf
microduck_rl/src/mjlab_microduck/robot/microduck/mjcf_to_urdf.py
microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml
microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions_backlash.xml
microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions_rollers.xml
microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions_rollers_backlash.xml
microduck_rl/src/mjlab_microduck/robot/microduck/robot_walk.xml
microduck_rl/src/mjlab_microduck/robot/microduck/robot_walk_backlash.xml
microduck_rl/src/mjlab_microduck/robot/microduck/scene.xml
microduck_rl/src/mjlab_microduck/robot/microduck/scene_backlash.xml
microduck_rl/src/mjlab_microduck/robot/microduck/scene_ball.xml
microduck_rl/src/mjlab_microduck/robot/microduck/scene_rollers.xml
microduck_rl/src/mjlab_microduck/robot/microduck/scene_walk.xml
microduck_rl/src/mjlab_microduck/robot/microduck/scene_walk_backlash.xml
microduck_rl/src/mjlab_microduck/robot/microduck/sensors.xml
microduck_rl/src/mjlab_microduck/robot/microduck_constants.py
microduck_rl/src/mjlab_microduck/robot/testbench_constants.py
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/arm.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/axis.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/bench_holder.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/part_1.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/part_2.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/part_3.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/part_4.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/part_5.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/spacer.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/weight.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/xl330.part
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/config.json
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/joints_properties.xml
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/scene.xml
microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/xl330_test_bench.xml
microduck_rl/src/mjlab_microduck/tasks/__init__.py
microduck_rl/src/mjlab_microduck/tasks/backlash.py
microduck_rl/src/mjlab_microduck/tasks/mdp.py
microduck_rl/src/mjlab_microduck/tasks/microduck_ball_kick_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_ground_pick_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_roller_crouch_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_roller_slope_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_roller_standup_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_roulade_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_spin_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_standup_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_velocity_rollers_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_velocity_swizzle_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/microduck_velstand_env_cfg.py
microduck_rl/src/mjlab_microduck/tasks/slope_terrain.py
microduck_rl/src/mjlab_microduck/tasks/symmetry.py
microduck_rl/src/mjlab_microduck/tasks/testbench_env_cfg.py
microduck_rl/src/mjlab_microduck/train_cli.py
microduck_rl/tests/test_aarch64_cuda_torch.py
microduck_rl/tests/test_crouch_glide.py
microduck_rl/tests/test_descent_speed.py
microduck_rl/tests/test_ground_pick_cfg.py
microduck_rl/tests/test_ground_pick_pose.py
microduck_rl/tests/test_head_pose_bias.py
microduck_rl/tests/test_nan_guard.py
microduck_rl/tests/test_obs_nan_guard.py
microduck_rl/tests/test_roller_crouch_cfg.py
microduck_rl/tests/test_roller_slope_cfg.py
microduck_rl/tests/test_roller_standup_cfg.py
microduck_rl/tests/test_slope_curriculum.py
microduck_rl/tests/test_slope_terrain.py
microduck_rl/tests/test_spin.py
microduck_rl/tests/test_spin_cfg.py
microduck_rl/tests/test_swizzle_head_cfg.py
microduck_rl/tests/test_wheel_glide.py
microduck_runtime/.github/workflows/release.yml
microduck_runtime/.gitignore
microduck_runtime/Cargo.toml
microduck_runtime/Cross.toml
microduck_runtime/README.md
microduck_runtime/build.rs
microduck_runtime/install.sh
microduck_runtime/policies/ground_pick.onnx
microduck_runtime/policies/standing.onnx
microduck_runtime/policies/standing_body_control.onnx
microduck_runtime/policies/walking.onnx
microduck_runtime/rpi_setup/.bashrc
microduck_runtime/rpi_setup/config.txt
microduck_runtime/rpi_setup/config_test.txt
microduck_runtime/rpi_setup/microduck_runtime.service
microduck_runtime/rpi_setup/setup.md
microduck_runtime/src/bin/calibrate_imu.rs
microduck_runtime/src/bin/check_voltage.rs
microduck_runtime/src/bin/debug_bno08x.rs
microduck_runtime/src/bin/em.rs
microduck_runtime/src/bin/init.rs
microduck_runtime/src/bin/microduck_help.rs
microduck_runtime/src/bin/test_controller.rs
microduck_runtime/src/bin/test_i2c_raw.rs
microduck_runtime/src/bin/test_imu.rs
microduck_runtime/src/controller.rs
microduck_runtime/src/imu.rs
microduck_runtime/src/lib.rs
microduck_runtime/src/main.rs
microduck_runtime/src/motor.rs
microduck_runtime/src/observation.rs
microduck_runtime/src/policy.rs
microduck_sounds/.gitignore
microduck_sounds/README.md
microduck_sounds/microduck_sounds/__init__.py
microduck_sounds/microduck_sounds/api.py
microduck_sounds/microduck_sounds/cli.py
microduck_sounds/microduck_sounds/parrot.py
microduck_sounds/microduck_sounds/personality.py
microduck_sounds/microduck_sounds/synth.py
microduck_sounds/microduck_sounds/voices.py
microduck_sounds/pyproject.toml
micropal/.github/workflows/release.yml
micropal/.gitignore
micropal/Package.swift
micropal/README.md
micropal/Scripts/build-app.sh
micropal/Scripts/make-dmg.sh
micropal/Scripts/make-icon.sh
micropal/Sources/Micropal/AppDelegate.swift
micropal/Sources/Micropal/Duck/DuckLayerView.swift
micropal/Sources/Micropal/Duck/DuckPalette.swift
micropal/Sources/Micropal/Duck/DuckPaths.swift
micropal/Sources/Micropal/Duck/DuckPose.swift
micropal/Sources/Micropal/Duck/DuckStyle.swift
micropal/Sources/Micropal/Engine/CursorTracker.swift
micropal/Sources/Micropal/Engine/DuckStateMachine.swift
micropal/Sources/Micropal/Engine/PetController.swift
micropal/Sources/Micropal/Engine/PetWindow.swift
micropal/Sources/Micropal/IconRenderer.swift
micropal/Sources/Micropal/Settings/SettingsStore.swift
micropal/Sources/Micropal/Settings/SettingsView.swift
micropal/Sources/Micropal/Settings/SettingsWindowController.swift
micropal/Sources/Micropal/StatusItemController.swift
micropal/Sources/Micropal/main.swift
micropal/Support/Info.plist
mjlab_microduck_waddle/.gitattributes
mjlab_microduck_waddle/.gitignore
mjlab_microduck_waddle/GUIDE.md
mjlab_microduck_waddle/README.md
mjlab_microduck_waddle/WADDLE_MJLAB_NOTES.md
mjlab_microduck_waddle/WADDLE_VISUAL_SIMULATION_GUIDE.md
mjlab_microduck_waddle/WADDLE_WALKING_TRAINING_GUIDE.md
mjlab_microduck_waddle/export.py
mjlab_microduck_waddle/pyproject.toml
mjlab_microduck_waddle/scripts/infer_policy.py
mjlab_microduck_waddle/scripts/plot_observations_comparison_plotly.py
mjlab_microduck_waddle/scripts/replay_reference_motion.py
mjlab_microduck_waddle/src/mjlab_microduck/__init__.py
mjlab_microduck_waddle/src/mjlab_microduck/data/.gitkeep
mjlab_microduck_waddle/src/mjlab_microduck/motion_loader.py
mjlab_microduck_waddle/src/mjlab_microduck/reference_motion.py
mjlab_microduck_waddle/src/mjlab_microduck/robot/__init__.py
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/additional.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/back_shell.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/bearing.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/bms.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/bno055.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/board.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/bottom_shell.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/camera_spacer.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/camshaft.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/cell.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/crossmember.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/foot.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/foot_tpu_bottom.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/front_shell.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/head_base_plate.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/head_pitch_to_yaw.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/head_top.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/head_yaw_to_roll.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/holder.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/jack.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/jumper.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/left_roll_to_pitch.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/leg_plate.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/long_neck_plate1.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/long_neck_plate2.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/mouth.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/neck_plate.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/neck_reinforcement.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/power_switch.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/raspberrypizerow.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/right_roll_to_pitch.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/roll_motor_bottom.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/roll_motor_top.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/spacer.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/teeth.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/top_shell.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/trunk.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/trunk_base.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/trunk_yaw.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/ubec_8v_5v_dc_dc.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/uc.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/uc_boards.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/uc_inside_holder.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/usb_c_charger.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/xl330.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/config_mjcf_ground_pick.json
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/config_mjcf_standup.json
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/config_mjcf_walk.json
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/config_urdf.json
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/joints_properties.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/robot.urdf
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/robot_ground_pick.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/robot_standup.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/robot_walk.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/scene.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/sensors.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck_constants.py
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/antenna.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/battery_enclosure.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/bno055.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/board.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/body_back.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/body_front.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/body_middle_bottom.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/body_middle_top.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/bulb.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/drive_palonier.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/flash_light_module.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/flash_reflector_interface.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/foot_bottom_pla.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/foot_bottom_tpu.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/foot_side.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/foot_top.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/full_speaker.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/glass.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/head.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/head_bot_sheet.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/head_pitch_to_yaw.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/head_roll_mount.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/head_yaw_to_roll.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/jetson_nano_baseplate.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/left_antenna_holder.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/left_cache.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/left_eye.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/left_knee_to_ankle_left_sheet.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/left_knee_to_ankle_right_sheet.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/left_roll_to_pitch.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/leg_spacer.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/neck_left_sheet.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/neck_right_sheet.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/passive_palonier.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/pdb_xt60.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/right_antenna_holder.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/right_cache.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/right_eye.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/right_roll_to_pitch.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/roll_bearing.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/roll_motor_bottom.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/roll_motor_top.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/sg90.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/simplified_jetson_nano.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/speaker_interface.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/speaker_stand.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/switch.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/trunk_bottom.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/trunk_top.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/turnigy_3s_battery.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/usb_camera_ov2710.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/wj_wk00_0122topcabinetcase_95.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/wj_wk00_0123middlecase_56.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/wj_wk00_0124bottomcase_45.part
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/config.json
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/joints_properties.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/scene_flat_terrain.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/scene_flat_terrain_backlash.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/scene_rough_terrain_NObacklash.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/sensors.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/waddle.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/xmls/waddle_12V_backlash.xml
mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle_constants.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/__init__.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/imitation_command.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/imitation_mdp.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/mdp.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/microduck_ground_pick_env_cfg.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/microduck_imitation_env_cfg.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/microduck_standup_env_cfg.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py
mjlab_microduck_waddle/src/mjlab_microduck/tasks/waddle_velocity_env_cfg.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `318_lab-microduck-simulator/app/public/assets` | 3 | 237 KB | [`318_lab-microduck-simulator/app/public/assets/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/assets/props` | 9 | 2.0 MB | [`318_lab-microduck-simulator/app/public/assets/props/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/props/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/assets/stickers` | 9 | 289 KB | [`318_lab-microduck-simulator/app/public/assets/stickers/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/stickers/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/assets/voices/duck1` | 18 | 358 KB | [`318_lab-microduck-simulator/app/public/assets/voices/duck1/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/voices/duck1/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/assets/voices/duck2` | 18 | 474 KB | [`318_lab-microduck-simulator/app/public/assets/voices/duck2/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/voices/duck2/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/assets/voices/duck3` | 18 | 447 KB | [`318_lab-microduck-simulator/app/public/assets/voices/duck3/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/voices/duck3/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/assets/voices/duck4` | 18 | 507 KB | [`318_lab-microduck-simulator/app/public/assets/voices/duck4/_OMITTED.md`](./318_lab-microduck-simulator/app/public/assets/voices/duck4/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/robot/mjlab` | 1 | 1.2 MB | [`318_lab-microduck-simulator/app/public/robot/mjlab/_OMITTED.md`](./318_lab-microduck-simulator/app/public/robot/mjlab/_OMITTED.md) |
| `318_lab-microduck-simulator/app/public/robot/mjlab/meshes` | 43 | 5.3 MB | [`318_lab-microduck-simulator/app/public/robot/mjlab/meshes/_OMITTED.md`](./318_lab-microduck-simulator/app/public/robot/mjlab/meshes/_OMITTED.md) |
| `ch_microduck` | 1 | 4.7 MB | [`ch_microduck/_OMITTED.md`](./ch_microduck/_OMITTED.md) |
| `microduck` | 1 | 131 KB | [`microduck/_OMITTED.md`](./microduck/_OMITTED.md) |
| `microduck-3d` | 46 | 24.6 MB | [`microduck-3d/_OMITTED.md`](./microduck-3d/_OMITTED.md) |
| `microduck-mcp` | 1 | 308 KB | [`microduck-mcp/_OMITTED.md`](./microduck-mcp/_OMITTED.md) |
| `microduck-mcp/docs/images` | 4 | 366 KB | [`microduck-mcp/docs/images/_OMITTED.md`](./microduck-mcp/docs/images/_OMITTED.md) |
| `microduck-miniverse` | 1 | 204 KB | [`microduck-miniverse/_OMITTED.md`](./microduck-miniverse/_OMITTED.md) |
| `microduck-miniverse/embodiments` | 2 | 13.8 MB | [`microduck-miniverse/embodiments/_OMITTED.md`](./microduck-miniverse/embodiments/_OMITTED.md) |
| `microduck-sandbox/app/public/assets` | 3 | 237 KB | [`microduck-sandbox/app/public/assets/_OMITTED.md`](./microduck-sandbox/app/public/assets/_OMITTED.md) |
| `microduck-sandbox/app/public/assets/props` | 9 | 2.0 MB | [`microduck-sandbox/app/public/assets/props/_OMITTED.md`](./microduck-sandbox/app/public/assets/props/_OMITTED.md) |
| `microduck-sandbox/app/public/assets/stickers` | 9 | 289 KB | [`microduck-sandbox/app/public/assets/stickers/_OMITTED.md`](./microduck-sandbox/app/public/assets/stickers/_OMITTED.md) |
| `microduck-sandbox/app/public/assets/voices/duck1` | 18 | 358 KB | [`microduck-sandbox/app/public/assets/voices/duck1/_OMITTED.md`](./microduck-sandbox/app/public/assets/voices/duck1/_OMITTED.md) |
| `microduck-sandbox/app/public/assets/voices/duck2` | 18 | 474 KB | [`microduck-sandbox/app/public/assets/voices/duck2/_OMITTED.md`](./microduck-sandbox/app/public/assets/voices/duck2/_OMITTED.md) |
| `microduck-sandbox/app/public/assets/voices/duck3` | 18 | 447 KB | [`microduck-sandbox/app/public/assets/voices/duck3/_OMITTED.md`](./microduck-sandbox/app/public/assets/voices/duck3/_OMITTED.md) |
| `microduck-sandbox/app/public/assets/voices/duck4` | 18 | 507 KB | [`microduck-sandbox/app/public/assets/voices/duck4/_OMITTED.md`](./microduck-sandbox/app/public/assets/voices/duck4/_OMITTED.md) |
| `microduck-sandbox/app/public/robot/mjlab` | 1 | 1.2 MB | [`microduck-sandbox/app/public/robot/mjlab/_OMITTED.md`](./microduck-sandbox/app/public/robot/mjlab/_OMITTED.md) |
| `microduck-sandbox/app/public/robot/mjlab/meshes` | 43 | 5.3 MB | [`microduck-sandbox/app/public/robot/mjlab/meshes/_OMITTED.md`](./microduck-sandbox/app/public/robot/mjlab/meshes/_OMITTED.md) |
| `microduck-simulator/app/public/assets` | 3 | 237 KB | [`microduck-simulator/app/public/assets/_OMITTED.md`](./microduck-simulator/app/public/assets/_OMITTED.md) |
| `microduck-simulator/app/public/assets/props` | 9 | 2.0 MB | [`microduck-simulator/app/public/assets/props/_OMITTED.md`](./microduck-simulator/app/public/assets/props/_OMITTED.md) |
| `microduck-simulator/app/public/assets/stickers` | 9 | 289 KB | [`microduck-simulator/app/public/assets/stickers/_OMITTED.md`](./microduck-simulator/app/public/assets/stickers/_OMITTED.md) |
| `microduck-simulator/app/public/assets/voices/duck1` | 18 | 358 KB | [`microduck-simulator/app/public/assets/voices/duck1/_OMITTED.md`](./microduck-simulator/app/public/assets/voices/duck1/_OMITTED.md) |
| `microduck-simulator/app/public/assets/voices/duck2` | 18 | 474 KB | [`microduck-simulator/app/public/assets/voices/duck2/_OMITTED.md`](./microduck-simulator/app/public/assets/voices/duck2/_OMITTED.md) |
| `microduck-simulator/app/public/assets/voices/duck3` | 18 | 447 KB | [`microduck-simulator/app/public/assets/voices/duck3/_OMITTED.md`](./microduck-simulator/app/public/assets/voices/duck3/_OMITTED.md) |
| `microduck-simulator/app/public/assets/voices/duck4` | 18 | 507 KB | [`microduck-simulator/app/public/assets/voices/duck4/_OMITTED.md`](./microduck-simulator/app/public/assets/voices/duck4/_OMITTED.md) |
| `microduck-simulator/app/public/robot/mjlab` | 1 | 1.2 MB | [`microduck-simulator/app/public/robot/mjlab/_OMITTED.md`](./microduck-simulator/app/public/robot/mjlab/_OMITTED.md) |
| `microduck-simulator/app/public/robot/mjlab/meshes` | 43 | 5.3 MB | [`microduck-simulator/app/public/robot/mjlab/meshes/_OMITTED.md`](./microduck-simulator/app/public/robot/mjlab/meshes/_OMITTED.md) |
| `microduck/robotctl/assets` | 1 | 67 KB | [`microduck/robotctl/assets/_OMITTED.md`](./microduck/robotctl/assets/_OMITTED.md) |
| `microduck/sounds/scores` | 2 | 8 KB | [`microduck/sounds/scores/_OMITTED.md`](./microduck/sounds/scores/_OMITTED.md) |
| `microduck/updater` | 1 | 3 KB | [`microduck/updater/_OMITTED.md`](./microduck/updater/_OMITTED.md) |
| `microduck_app/public/icons` | 3 | 3 KB | [`microduck_app/public/icons/_OMITTED.md`](./microduck_app/public/icons/_OMITTED.md) |
| `microduck_app/public/robot/alpha/meshes` | 34 | 19.2 MB | [`microduck_app/public/robot/alpha/meshes/_OMITTED.md`](./microduck_app/public/robot/alpha/meshes/_OMITTED.md) |
| `microduck_app/public/robot/v1.5/meshes` | 32 | 13.7 MB | [`microduck_app/public/robot/v1.5/meshes/_OMITTED.md`](./microduck_app/public/robot/v1.5/meshes/_OMITTED.md) |
| `microduck_app/public/robot/v1/meshes` | 27 | 8.8 MB | [`microduck_app/public/robot/v1/meshes/_OMITTED.md`](./microduck_app/public/robot/v1/meshes/_OMITTED.md) |
| `microduck_app/robot_assets/alpha/assets` | 34 | 19.2 MB | [`microduck_app/robot_assets/alpha/assets/_OMITTED.md`](./microduck_app/robot_assets/alpha/assets/_OMITTED.md) |
| `microduck_app/robot_assets/v1.5/assets` | 32 | 13.7 MB | [`microduck_app/robot_assets/v1.5/assets/_OMITTED.md`](./microduck_app/robot_assets/v1.5/assets/_OMITTED.md) |
| `microduck_app/robot_assets/v1/assets` | 27 | 8.8 MB | [`microduck_app/robot_assets/v1/assets/_OMITTED.md`](./microduck_app/robot_assets/v1/assets/_OMITTED.md) |
| `microduck_kinematics_rs` | 1 | 7 KB | [`microduck_kinematics_rs/_OMITTED.md`](./microduck_kinematics_rs/_OMITTED.md) |
| `microduck_kinematics_rs/scripts` | 1 | 64 KB | [`microduck_kinematics_rs/scripts/_OMITTED.md`](./microduck_kinematics_rs/scripts/_OMITTED.md) |
| `microduck_maploc_rs` | 1 | 185 KB | [`microduck_maploc_rs/_OMITTED.md`](./microduck_maploc_rs/_OMITTED.md) |
| `microduck_pet_detect` | 1 | 11 KB | [`microduck_pet_detect/_OMITTED.md`](./microduck_pet_detect/_OMITTED.md) |
| `microduck_rl` | 1 | 238 KB | [`microduck_rl/_OMITTED.md`](./microduck_rl/_OMITTED.md) |
| `microduck_rl/src/mjlab_microduck/robot` | 1 | 8.9 MB | [`microduck_rl/src/mjlab_microduck/robot/_OMITTED.md`](./microduck_rl/src/mjlab_microduck/robot/_OMITTED.md) |
| `microduck_rl/src/mjlab_microduck/robot/microduck/assets` | 47 | 24.9 MB | [`microduck_rl/src/mjlab_microduck/robot/microduck/assets/_OMITTED.md`](./microduck_rl/src/mjlab_microduck/robot/microduck/assets/_OMITTED.md) |
| `microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets` | 11 | 756 KB | [`microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/_OMITTED.md`](./microduck_rl/src/mjlab_microduck/robot/xl330_test_bench/assets/_OMITTED.md) |
| `microduck_runtime` | 1 | 37 KB | [`microduck_runtime/_OMITTED.md`](./microduck_runtime/_OMITTED.md) |
| `microduck_sounds` | 1 | 54 KB | [`microduck_sounds/_OMITTED.md`](./microduck_sounds/_OMITTED.md) |
| `micropal/docs` | 5 | 214 KB | [`micropal/docs/_OMITTED.md`](./micropal/docs/_OMITTED.md) |
| `mjlab_microduck_waddle` | 1 | 309 KB | [`mjlab_microduck_waddle/_OMITTED.md`](./mjlab_microduck_waddle/_OMITTED.md) |
| `mjlab_microduck_waddle/src/mjlab_microduck/data` | 1 | 91.7 MB | [`mjlab_microduck_waddle/src/mjlab_microduck/data/_OMITTED.md`](./mjlab_microduck_waddle/src/mjlab_microduck/data/_OMITTED.md) |
| `mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets` | 44 | 9.7 MB | [`mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/_OMITTED.md`](./mjlab_microduck_waddle/src/mjlab_microduck/robot/microduck/assets/_OMITTED.md) |
| `mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets` | 55 | 13.2 MB | [`mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/_OMITTED.md`](./mjlab_microduck_waddle/src/mjlab_microduck/robot/waddle/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
