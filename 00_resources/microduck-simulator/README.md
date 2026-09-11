# microduck-simulator — 参考资源

> **来源**：`00_open/microduck-simulator/`　｜　**类型**：参考项目
> **关联机型**：microduck（MicroDuck 双足）
> **定位**：MicroDuck 仿真器
> **收录**：58 个文件 / 7.4 MB（其中推理策略/模型文件 9 个）
> **已省略**：147 个文件 / 10.9 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（3 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（2 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（1 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（10 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（42 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
app/  （54 个文件）
    (直接文件)/
    public/
    src/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.js` | 23 |
| `.jsx` | 12 |
| `.onnx` | 9 |
| `(无扩展名)` | 4 |
| `.json` | 4 |
| `.html` | 3 |
| `.xml` | 2 |
| `.md` | 1 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.gitignore
Dockerfile
README.md
app/.gitignore
app/index.html
app/package-lock.json
app/package.json
app/public/policies/BEST_alpha_sitstand.onnx
app/public/policies/BEST_alpha_stand.onnx
app/public/policies/BEST_alpha_walking.onnx
app/public/policies/BEST_roller.onnx
app/public/policies/BEST_roller_crouch.onnx
app/public/policies/alpha_ground_pick.onnx
app/public/policies/ball_kick_left.onnx
app/public/policies/ball_kick_right.onnx
app/public/policies/roulade.onnx
app/public/robot/mjlab/kinematics.json
app/public/robot/mjlab/kinematics_rollers.json
app/public/robot/mjlab/robot_allcollisions.xml
app/public/robot/mjlab/robot_allcollisions_rollers.xml
app/src/App.jsx
app/src/game/arena.js
app/src/game/audio.js
app/src/game/ball-actor.js
app/src/game/ball-visual.js
app/src/game/ceremony.js
app/src/game/constants.js
app/src/game/controls/controller.js
app/src/game/controls/gamepad.js
app/src/game/controls/keyboard.js
app/src/game/controls/touch.js
app/src/game/duck.js
app/src/game/fx/demo-glitch.html
app/src/game/fx/demo-wireframe.html
app/src/game/fx/fx-glitch.js
app/src/game/fx/fx-wireframe.js
app/src/game/game.js
app/src/game/ghosts.js
app/src/game/props.js
app/src/game/signed.js
app/src/game/stickers.js
app/src/game/variants.js
app/src/game/vendor/zzfx.js
app/src/main.jsx
app/src/scene/CrtDistortion.jsx
app/src/scene/GameCanvas.jsx
app/src/store.js
app/src/theme.js
app/src/ui/BiosOverlay.jsx
app/src/ui/Hud.jsx
app/src/ui/MenuDuck.jsx
app/src/ui/Overlays.jsx
app/src/ui/Soundboard.jsx
app/src/ui/TitleMenu.jsx
app/src/ui/TouchOverlay.jsx
app/src/ui/comic.jsx
app/vite.config.js
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `app/public/assets` | 3 | 237 KB | [`app/public/assets/_OMITTED.md`](./app/public/assets/_OMITTED.md) |
| `app/public/assets/props` | 9 | 2.0 MB | [`app/public/assets/props/_OMITTED.md`](./app/public/assets/props/_OMITTED.md) |
| `app/public/assets/sfx` | 10 | 84 KB | [`app/public/assets/sfx/_OMITTED.md`](./app/public/assets/sfx/_OMITTED.md) |
| `app/public/assets/stickers` | 9 | 289 KB | [`app/public/assets/stickers/_OMITTED.md`](./app/public/assets/stickers/_OMITTED.md) |
| `app/public/assets/voices/duck1` | 18 | 358 KB | [`app/public/assets/voices/duck1/_OMITTED.md`](./app/public/assets/voices/duck1/_OMITTED.md) |
| `app/public/assets/voices/duck2` | 18 | 474 KB | [`app/public/assets/voices/duck2/_OMITTED.md`](./app/public/assets/voices/duck2/_OMITTED.md) |
| `app/public/assets/voices/duck3` | 18 | 447 KB | [`app/public/assets/voices/duck3/_OMITTED.md`](./app/public/assets/voices/duck3/_OMITTED.md) |
| `app/public/assets/voices/duck4` | 18 | 507 KB | [`app/public/assets/voices/duck4/_OMITTED.md`](./app/public/assets/voices/duck4/_OMITTED.md) |
| `app/public/robot/mjlab` | 1 | 1.2 MB | [`app/public/robot/mjlab/_OMITTED.md`](./app/public/robot/mjlab/_OMITTED.md) |
| `app/public/robot/mjlab/meshes` | 43 | 5.3 MB | [`app/public/robot/mjlab/meshes/_OMITTED.md`](./app/public/robot/mjlab/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
