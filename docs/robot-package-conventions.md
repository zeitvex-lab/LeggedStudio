# 机器人包目录约定（robot package conventions）

> 适用于 `assets/robots/<robot_id>/` 与工作区导入的包。
> 参考来源：unitree_rl_mjlab deploy 三级布局与碰撞精简做法；robot_lab 自描述 motion NPZ schema 与框架无关常量模块。

## 目录布局

```
<robot_id>/
  contract.json              # RobotContractV2（尺寸/关节/观测/动作/控制契约，schema robot-contract-2.0）
  robot_package.json         # 包清单（schema robot-package-1.0）
  model/
    robot.xml                # MJCF 最终产物（visual/collision 双 class 分层；碰撞用原始体）
    assets/                  # 网格（记录精简结论：如 "9 boxes + 4 spheres + 4 wheel cylinders"）
  simulation/
    config.json              # schema simulation-config-1.0（增益/decimation/策略条目）
    scene.xml                # 平地场景（include 机器人；桌面端 include+meshdir 有已知坑，见 OPEN_QUESTIONS）
    flat.xml / *.xml         # 浏览器可选场景
    policies/
      <name>.onnx            # 导出策略（建议含 metadata_props 盖章，见 policy-contract-and-acceptance.md）
      <name>.acceptance.json # 验收指标（schema policy-acceptance-1.0，与 onnx 同名）
  training/
    config.json              # 训练入口配置
    profiles/*.json          # 训练 profile（training-profile-1.0）
  motions/                   # （预留）参考动作
    <name>.csv               # 原始重定向数据（可追溯源文件）
    <name>.npz               # 自描述 NPZ：fps/dof_names/body_names/dof_positions/
                             #   body_rotations(wxyz)/body_*_velocities
  acceptance/                # （预留）验收参考档案：参考 episode 录制 + 通过阈值
```

## capabilities（robot_package.json）

能力声明用于枚举门控（robot_lab register/detect 模式）：

| capability | 含义 | 谁消费 |
|---|---|---|
| `generic_mjlab` | 可被通用 mjlab 任务训练 | 训练配置页 / worker |
| `mjlab_source_profiles` | 包内带 mjlab 源码 profile | 训练配置页 |
| `mujoco_sim` | 可进浏览器 MuJoCo 仿真 | `browser-config` 422 门控 |
| `package_extension` | 带扩展任务源 | worker 扩展加载 |

新增能力时：robot_package.json 声明 → `backend/robot_packages.py` 枚举透传（已支持）→ 消费端按需门控。

## 命名与校验规则

- 验收指标文件名 = `<onnx stem>.acceptance.json`，与策略同目录；`browser-config` 自动折算为
  策略健康检查 `acceptance`。
- 策略元数据盖章键名见 `docs/policy-contract-and-acceptance.md`；浏览器加载时自动校验
  `joint_names` 顺序与契约 `action_joint_order` 一致。
- motions NPZ 的 `dof_names` 必须与 `contract.json → joints.actuated_joints` 一致（导入时可校验）。
- 部署参数（若单独成文件）数组长度必须等于 `action.dimension` / `observation.dimension`。

## LLoco 桥接（external source_root 模式）

`training/source_lloco/lloco_bridge/` 是外部训练源仓库（`lain_job/LLoco`，mjlab==1.6.0
Apache-2.0）的薄桥：把 LLoco 的 `src` 加入 sys.path 并把带参工厂
（`make_flat_env_cfg(profile)`）适配成 worker 契约的无参 `module:factory`。

- profile：`training/profiles/lloco-go2-flat.json`（entrypoints 指向 bridge）
- 冒烟已验证：env 构建 / reset / step / reward 全通；worker `_load_profile_bundle` 加载通过
- **注意**：运行时读取的是 `workspace/packages/<id>/` 副本——assets 与 workspace 两边都要放
  （capabilities、profiles、bridge 同步），改包后需 `POST /api/robots/packages/refresh`
- 扩展：给其他机器人加 LLoco 任务只需在 bridge 的 `_PROFILE_BY_KEY` 加一行
