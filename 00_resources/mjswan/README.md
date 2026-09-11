# mjswan — 参考资源

> **来源**：`00_open/mjswan/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go1（宇树 Go1 四足）、unitree_g1（宇树 G1 人形）
> **定位**：mjlab 可视化/仿真套件
> **收录**：380 个文件 / 22.7 MB（其中推理策略/模型文件 11 个）
> **已省略**：91 个文件 / 103.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（25 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（22 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（13 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（7 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（70 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（242 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （11 个文件）
.claude/  （5 个文件）
    (直接文件)/
    commands/
.claude-plugin/  （2 个文件）
    (直接文件)/
.github/  （11 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
    workflows/
docs/  （25 个文件）
    (直接文件)/
    adr/
    docs/
examples/  （67 个文件）
    colab/
    demo/
    mjlab/
    tutorial/
scripts/  （1 个文件）
    (直接文件)/
skills/  （3 个文件）
    mjlab-to-mjswan/
src/  （199 个文件）
    mjswan/
tests/  （41 个文件）
    (直接文件)/
typings/  （15 个文件）
    (直接文件)/
    mujoco/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.ts` | 124 |
| `.py` | 106 |
| `.md` | 40 |
| `.json` | 18 |
| `(无扩展名)` | 14 |
| `.pyi` | 14 |
| `.yml` | 11 |
| `.onnx` | 11 |
| `.xml` | 10 |
| `.tsx` | 9 |
| `.ipynb` | 5 |
| `.txt` | 3 |
| `.yaml` | 2 |
| `.toml` | 2 |
| `.cjs` | 2 |

## 文件索引（项目内相对路径）

```text
.claude-plugin/marketplace.json
.claude-plugin/plugin.json
.claude/CLAUDE.md
.claude/commands/commit-message.md
.claude/commands/commit-push-pr.md
.claude/commands/simplify-comments.md
.claude/settings.json
.github/FUNDING.yml
.github/ISSUE_TEMPLATE/bug_report.yml
.github/workflows/deploy.yml
.github/workflows/frontend.yml
.github/workflows/parity.yml
.github/workflows/publish-npm.yml
.github/workflows/publish-pypi.yml
.github/workflows/pytest.yml
.github/workflows/release.yml
.github/workflows/ruff.yml
.github/workflows/sync-contributors.yml
.gitignore
.pre-commit-config.yaml
.python-version
AGENTS.md
CHANGELOG.md
CITATION.cff
CONTEXT.md
LICENSE
Makefile
README.md
docs/.readthedocs.yaml
docs/README.md
docs/adr/0001-npm-self-reference-for-custom-mdp-imports.md
docs/adr/0002-muscle-action-term-aligned-with-myomuscleactivationactioncfg.md
docs/adr/0003-declarative-mdp-terms-alongside-custom-js.md
docs/adr/0004-headless-engine-core.md
docs/adr/0005-onnx-traced-terms-superseding-the-declarative-dsl.md
docs/adr/0006-swn-simulation-document.md
docs/docs/api/core.md
docs/docs/api/engine.md
docs/docs/getting-started/cli.md
docs/docs/getting-started/core-concepts.md
docs/docs/getting-started/examples.md
docs/docs/getting-started/installation.md
docs/docs/getting-started/quickstart.md
docs/docs/guides/deployment.md
docs/docs/guides/embedding.md
docs/docs/guides/how-it-works.md
docs/docs/guides/mjlab.md
docs/docs/guides/policy-config.md
docs/docs/guides/publishing.md
docs/docs/index.md
docs/docs/resources.md
docs/requirements.txt
docs/zensical.toml
examples/colab/anymal_c_velocity.ipynb
examples/colab/demo.ipynb
examples/demo/assets/anymal_c_velocity/Mjlab-Velocity-Flat-Anymal-C.3000.json
examples/demo/assets/anymal_c_velocity/Mjlab-Velocity-Flat-Anymal-C.3000.onnx
examples/demo/assets/unitree_g1/LICENSE
examples/demo/assets/unitree_g1/README.md
examples/demo/assets/unitree_g1/balance.json
examples/demo/assets/unitree_g1/balance.onnx
examples/demo/assets/unitree_g1/g1.xml
examples/demo/assets/unitree_g1/g1_with_hands.xml
examples/demo/assets/unitree_g1/locomotion.json
examples/demo/assets/unitree_g1/locomotion.onnx
examples/demo/assets/unitree_g1/scene.xml
examples/demo/assets/unitree_g1/scene_with_hands.xml
examples/demo/assets/unitree_g1/street.spz
examples/demo/assets/unitree_go1/LICENSE
examples/demo/assets/unitree_go1/decap.json
examples/demo/assets/unitree_go1/decap.onnx
examples/demo/assets/unitree_go1/go1.xml
examples/demo/assets/unitree_go1/himloco.json
examples/demo/assets/unitree_go1/himloco.onnx
examples/demo/assets/unitree_go2/LICENSE
examples/demo/assets/unitree_go2/README.md
examples/demo/assets/unitree_go2/facet.json
examples/demo/assets/unitree_go2/facet.onnx
examples/demo/assets/unitree_go2/go2.xml
examples/demo/assets/unitree_go2/go2_mjx.xml
examples/demo/assets/unitree_go2/go2_test.xml
examples/demo/assets/unitree_go2/robust.json
examples/demo/assets/unitree_go2/robust.onnx
examples/demo/assets/unitree_go2/scene.xml
examples/demo/assets/unitree_go2/scene_mjx.xml
examples/demo/assets/unitree_go2/vanilla.json
examples/demo/assets/unitree_go2/vanilla.onnx
examples/demo/gentle_humanoid/.gitignore
examples/demo/gentle_humanoid/main.py
examples/demo/gentle_humanoid/terms.py
examples/demo/main.py
examples/demo/muscle.py
examples/demo/simple.py
examples/demo/splat.py
examples/mjlab/defaults/README.md
examples/mjlab/defaults/commands/__init__.py
examples/mjlab/defaults/main.py
examples/mjlab/defaults/terminations/__init__.py
examples/mjlab/defaults/train.ipynb
examples/mjlab/g1_spinkick/README.md
examples/mjlab/g1_spinkick/main.py
examples/mjlab/g1_spinkick/train.ipynb
examples/mjlab/musclemimic/.gitignore
examples/mjlab/musclemimic/README.md
examples/mjlab/musclemimic/main.py
examples/mjlab/musclemimic/observations/MimicObservations.ts
examples/mjlab/musclemimic/observations/__init__.py
examples/mjlab/musclemimic/play.py
examples/mjlab/musclemimic/requirements.txt
examples/mjlab/musclemimic/terminations/MimicDeviation.ts
examples/mjlab/musclemimic/terminations/__init__.py
examples/mjlab/myosuite/README.md
examples/mjlab/myosuite/main.py
examples/mjlab/unitree_rl/.gitignore
examples/mjlab/unitree_rl/README.md
examples/mjlab/unitree_rl/main.py
examples/mjlab/unitree_rl/train.ipynb
examples/tutorial/hello_world.py
examples/tutorial/minimum_policy.py
examples/tutorial/mujoco_models.py
pyproject.toml
scripts/sync_contributors.py
skills/mjlab-to-mjswan/README.md
skills/mjlab-to-mjswan/SKILL.md
skills/mjlab-to-mjswan/export_policy.py
src/mjswan/__init__.py
src/mjswan/_build_client.py
src/mjswan/_cli.py
src/mjswan/_compat.py
src/mjswan/_graph_io.py
src/mjswan/_onnx_build.py
src/mjswan/adapters/__init__.py
src/mjswan/adapters/gui_spy.py
src/mjswan/adapters/mjlab_adapter.py
src/mjswan/adapters/mjlab_compat.py
src/mjswan/app.py
src/mjswan/auth.py
src/mjswan/builder.py
src/mjswan/command.py
src/mjswan/compile/__init__.py
src/mjswan/compile/parity.py
src/mjswan/compile/rng.py
src/mjswan/compile/serialize.py
src/mjswan/compile/tracer.py
src/mjswan/document.py
src/mjswan/envs/__init__.py
src/mjswan/envs/mdp/__init__.py
src/mjswan/envs/mdp/actions/__init__.py
src/mjswan/envs/mdp/actions/actions.py
src/mjswan/envs/mdp/commands.py
src/mjswan/envs/mdp/events.py
src/mjswan/envs/mdp/observations.py
src/mjswan/envs/mdp/terminations.py
src/mjswan/managers/__init__.py
src/mjswan/managers/action_manager.py
src/mjswan/managers/event_manager.py
src/mjswan/managers/observation_manager.py
src/mjswan/managers/termination_manager.py
src/mjswan/mdp.py
src/mjswan/motion.py
src/mjswan/policy.py
src/mjswan/project.py
src/mjswan/publish.py
src/mjswan/py.typed
src/mjswan/scene.py
src/mjswan/splat.py
src/mjswan/template/.browserslistrc
src/mjswan/template/.gitignore
src/mjswan/template/.npmrc
src/mjswan/template/LICENSE
src/mjswan/template/README.md
src/mjswan/template/_mt/coi-serviceworker.js
src/mjswan/template/e2e/engine.spec.ts
src/mjswan/template/e2e/env.d.ts
src/mjswan/template/eslint.config.cjs
src/mjswan/template/harness.html
src/mjswan/template/index.html
src/mjswan/template/lib.d.ts
src/mjswan/template/manifest.d.ts
src/mjswan/template/package-lock.json
src/mjswan/template/package.json
src/mjswan/template/playwright.config.ts
src/mjswan/template/public/robots.txt
src/mjswan/template/src/App.css.ts
src/mjswan/template/src/App.tsx
src/mjswan/template/src/AppTheme.ts
src/mjswan/template/src/ControlPanel/CommandSection.tsx
src/mjswan/template/src/ControlPanel/ControlPanel.tsx
src/mjswan/template/src/ControlPanel/FloatingPanel.tsx
src/mjswan/template/src/ControlPanel/LabeledInput.tsx
src/mjswan/template/src/ControlPanel/SplatSection.tsx
src/mjswan/template/src/ControlPanel/__tests__/SliderRange.test.ts
src/mjswan/template/src/ControlPanel/index.ts
src/mjswan/template/src/Version.ts
src/mjswan/template/src/components/Loader.css
src/mjswan/template/src/components/Loader.tsx
src/mjswan/template/src/contexts/LoadingContext.tsx
src/mjswan/template/src/core/__tests__/rng.test.ts
src/mjswan/template/src/core/action/__tests__/applyAction.test.ts
src/mjswan/template/src/core/action/applyAction.ts
src/mjswan/template/src/core/command/CommandManager.ts
src/mjswan/template/src/core/command/OnnxCommand.ts
src/mjswan/template/src/core/command/TrackingCommand.ts
src/mjswan/template/src/core/command/__tests__/CommandManager.test.ts
src/mjswan/template/src/core/command/__tests__/OnnxCommand.test.ts
src/mjswan/template/src/core/command/__tests__/TrackingCommand.test.ts
src/mjswan/template/src/core/command/__tests__/debugViz.test.ts
src/mjswan/template/src/core/command/debugViz.ts
src/mjswan/template/src/core/command/index.ts
src/mjswan/template/src/core/command/types.ts
src/mjswan/template/src/core/engine/__tests__/cameraTracking.test.ts
src/mjswan/template/src/core/engine/__tests__/fixtures/rollout/Mjlab-Cartpole-Balance/obs/policy.onnx
src/mjswan/template/src/core/engine/__tests__/fixtures/rollout/Mjlab-Velocity-Flat-Unitree-G1/obs/policy.onnx
src/mjswan/template/src/core/engine/__tests__/fixtures/rollout/Mjlab-Velocity-Flat-Unitree-G1/term/fell_over.onnx
src/mjswan/template/src/core/engine/__tests__/fixtures/rollout/rollout.json
src/mjswan/template/src/core/engine/__tests__/resetChain.test.ts
src/mjswan/template/src/core/engine/__tests__/rolloutParity.test.ts
src/mjswan/template/src/core/engine/resetChain.ts
src/mjswan/template/src/core/engine/runtime.ts
src/mjswan/template/src/core/engine/viewer_config.ts
src/mjswan/template/src/core/event/EventBase.ts
src/mjswan/template/src/core/event/EventManager.ts
src/mjswan/template/src/core/event/OnnxEvent.ts
src/mjswan/template/src/core/event/__tests__/EventManager.test.ts
src/mjswan/template/src/core/event/__tests__/OnnxEvent.test.ts
src/mjswan/template/src/core/event/__tests__/entityWrite.test.ts
src/mjswan/template/src/core/event/__tests__/modelFieldDr.test.ts
src/mjswan/template/src/core/event/__tests__/triggers.test.ts
src/mjswan/template/src/core/event/entityWrite.ts
src/mjswan/template/src/core/event/events.ts
src/mjswan/template/src/core/event/modelFieldDr.ts
src/mjswan/template/src/core/event/triggers.ts
src/mjswan/template/src/core/observation/FusedObservation.ts
src/mjswan/template/src/core/observation/HistoryObservation.ts
src/mjswan/template/src/core/observation/NativeObservation.ts
src/mjswan/template/src/core/observation/ObservationBase.ts
src/mjswan/template/src/core/observation/OnnxObservation.ts
src/mjswan/template/src/core/observation/__tests__/FusedObservation.test.ts
src/mjswan/template/src/core/observation/__tests__/HistoryObservation.test.ts
src/mjswan/template/src/core/observation/__tests__/OnnxObservation.test.ts
src/mjswan/template/src/core/observation/index.ts
src/mjswan/template/src/core/observation/math.ts
src/mjswan/template/src/core/observation/pipeline.ts
src/mjswan/template/src/core/onnx/__tests__/contact.test.ts
src/mjswan/template/src/core/onnx/__tests__/fixtures/slotFields.json
src/mjswan/template/src/core/onnx/__tests__/graphRefs.test.ts
src/mjswan/template/src/core/onnx/__tests__/raycast.test.ts
src/mjswan/template/src/core/onnx/__tests__/runQueue.test.ts
src/mjswan/template/src/core/onnx/__tests__/session.test.ts
src/mjswan/template/src/core/onnx/__tests__/slotReader.test.ts
src/mjswan/template/src/core/onnx/__tests__/slotReaderParity.test.ts
src/mjswan/template/src/core/onnx/contact.ts
src/mjswan/template/src/core/onnx/graphRefs.ts
src/mjswan/template/src/core/onnx/raycast.ts
src/mjswan/template/src/core/onnx/runQueue.ts
src/mjswan/template/src/core/onnx/session.ts
src/mjswan/template/src/core/onnx/slotReader.ts
src/mjswan/template/src/core/plugins.ts
src/mjswan/template/src/core/policy/OnnxModule.ts
src/mjswan/template/src/core/policy/PolicyModule.ts
src/mjswan/template/src/core/policy/PolicyRunner.ts
src/mjswan/template/src/core/policy/PolicyStateBuilder.ts
src/mjswan/template/src/core/policy/__tests__/groupHistory.test.ts
src/mjswan/template/src/core/policy/default_slots.json
src/mjswan/template/src/core/policy/modules/LocomotionPolicy.ts
src/mjswan/template/src/core/policy/modules/TrackingPolicy.ts
src/mjswan/template/src/core/policy/types.ts
src/mjswan/template/src/core/rng.ts
src/mjswan/template/src/core/scene/__tests__/lightSpecularRatio.test.ts
src/mjswan/template/src/core/scene/__tests__/reflectanceParams.test.ts
src/mjswan/template/src/core/scene/collider.ts
src/mjswan/template/src/core/scene/coordinate.ts
src/mjswan/template/src/core/scene/lights.ts
src/mjswan/template/src/core/scene/npz.ts
src/mjswan/template/src/core/scene/scene.ts
src/mjswan/template/src/core/scene/splat.ts
src/mjswan/template/src/core/scene/tendons.ts
src/mjswan/template/src/core/scene/textures.ts
src/mjswan/template/src/core/termination/FusedTermination.ts
src/mjswan/template/src/core/termination/OnnxTermination.ts
src/mjswan/template/src/core/termination/TerminationBase.ts
src/mjswan/template/src/core/termination/TerminationManager.ts
src/mjswan/template/src/core/termination/TimeOutTermination.ts
src/mjswan/template/src/core/termination/__tests__/OnnxTermination.test.ts
src/mjswan/template/src/core/termination/terminations.ts
src/mjswan/template/src/core/types.ts
src/mjswan/template/src/core/utils/bytes.ts
src/mjswan/template/src/core/utils/dragStateManager.ts
src/mjswan/template/src/core/utils/mjzLoader.ts
src/mjswan/template/src/core/utils/readySignal.ts
src/mjswan/template/src/core/xr/__tests__/grounding.test.ts
src/mjswan/template/src/core/xr/__tests__/handMocap.test.ts
src/mjswan/template/src/core/xr/__tests__/locomotion.test.ts
src/mjswan/template/src/core/xr/__tests__/passthrough.test.ts
src/mjswan/template/src/core/xr/arButton.ts
src/mjswan/template/src/core/xr/grounding.ts
src/mjswan/template/src/core/xr/handMocap.ts
src/mjswan/template/src/core/xr/locomotion.ts
src/mjswan/template/src/core/xr/passthrough.ts
src/mjswan/template/src/engine/createEngine.ts
src/mjswan/template/src/engine/harness.ts
src/mjswan/template/src/engine/index.ts
src/mjswan/template/src/engine/plugin-three-shim.cjs
src/mjswan/template/src/engine/types.ts
src/mjswan/template/src/harness/e2e-entry.ts
src/mjswan/template/src/index.css
src/mjswan/template/src/index.tsx
src/mjswan/template/src/manifest/index.test.ts
src/mjswan/template/src/manifest/index.ts
src/mjswan/template/src/manifest/name2id_cases.json
src/mjswan/template/src/types/three.d.ts
src/mjswan/template/src/urlState.test.ts
src/mjswan/template/src/urlState.ts
src/mjswan/template/src/vite-env.d.ts
src/mjswan/template/tsconfig.json
src/mjswan/template/vite.config.ts
src/mjswan/template/vite.lib.config.ts
src/mjswan/template/vite.manifest.config.ts
src/mjswan/template/vite.shared.ts
src/mjswan/template/vitest.config.ts
src/mjswan/trace_env.py
src/mjswan/utils.py
src/mjswan/viewer.py
src/mjswan/wandb_io.py
tests/conftest.py
tests/dump_rollout_fixture.py
tests/dump_slot_fixture.py
tests/rsi_body_fixture.py
tests/test_action_clip.py
tests/test_app.py
tests/test_artifact_hygiene.py
tests/test_auth.py
tests/test_builder.py
tests/test_commands.py
tests/test_compat.py
tests/test_constant_observation_group.py
tests/test_contact_sensor_descriptor.py
tests/test_dependency_versions.py
tests/test_document.py
tests/test_graph_io.py
tests/test_gui_spy.py
tests/test_last_action_slice.py
tests/test_lib_build.py
tests/test_mdp.py
tests/test_mjlab_adapter.py
tests/test_mjlab_compat.py
tests/test_motion.py
tests/test_muscle_action.py
tests/test_muscle_activation_transform.py
tests/test_native_observation_size.py
tests/test_obs_normalizer_alignment.py
tests/test_observation_history.py
tests/test_onnx_command_config.py
tests/test_onnx_command_parity.py
tests/test_onnx_event_config.py
tests/test_onnx_parity.py
tests/test_project.py
tests/test_publish.py
tests/test_raycast_sensor_descriptor.py
tests/test_splat.py
tests/test_trace_env.py
tests/test_trace_env_commands.py
tests/test_utils.py
tests/test_velocity_command.py
tests/test_wandb_io.py
typings/generate_mujoco_stubs.sh
typings/mujoco/__init__.pyi
typings/mujoco/_callbacks.pyi
typings/mujoco/_constants.pyi
typings/mujoco/_enums.pyi
typings/mujoco/_errors.pyi
typings/mujoco/_functions.pyi
typings/mujoco/_render.pyi
typings/mujoco/_specs.pyi
typings/mujoco/_structs.pyi
typings/mujoco/cgl/__init__.pyi
typings/mujoco/cgl/cgl.pyi
typings/mujoco/gl_context.pyi
typings/mujoco/renderer.pyi
typings/mujoco/viewer.pyi
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 565 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `assets` | 2 | 4.5 MB | [`assets/_OMITTED.md`](./assets/_OMITTED.md) |
| `docs/docs/assets` | 1 | 6 KB | [`docs/docs/assets/_OMITTED.md`](./docs/docs/assets/_OMITTED.md) |
| `examples/demo/assets/anymal_c_velocity` | 1 | 12.4 MB | [`examples/demo/assets/anymal_c_velocity/_OMITTED.md`](./examples/demo/assets/anymal_c_velocity/_OMITTED.md) |
| `examples/demo/assets/unitree_g1` | 2 | 3.4 MB | [`examples/demo/assets/unitree_g1/_OMITTED.md`](./examples/demo/assets/unitree_g1/_OMITTED.md) |
| `examples/demo/assets/unitree_g1/assets` | 51 | 34.3 MB | [`examples/demo/assets/unitree_g1/assets/_OMITTED.md`](./examples/demo/assets/unitree_g1/assets/_OMITTED.md) |
| `examples/demo/assets/unitree_go1/meshes` | 5 | 7.5 MB | [`examples/demo/assets/unitree_go1/meshes/_OMITTED.md`](./examples/demo/assets/unitree_go1/meshes/_OMITTED.md) |
| `examples/demo/assets/unitree_go2` | 2 | 2.3 MB | [`examples/demo/assets/unitree_go2/_OMITTED.md`](./examples/demo/assets/unitree_go2/_OMITTED.md) |
| `examples/demo/assets/unitree_go2/assets` | 16 | 27.8 MB | [`examples/demo/assets/unitree_go2/assets/_OMITTED.md`](./examples/demo/assets/unitree_go2/assets/_OMITTED.md) |
| `examples/demo/assets/unitree_go2/meshes` | 7 | 9.4 MB | [`examples/demo/assets/unitree_go2/meshes/_OMITTED.md`](./examples/demo/assets/unitree_go2/meshes/_OMITTED.md) |
| `src/mjswan/template/public` | 1 | 6 KB | [`src/mjswan/template/public/_OMITTED.md`](./src/mjswan/template/public/_OMITTED.md) |
| `src/mjswan/template/public/fixtures` | 1 | 725 B | [`src/mjswan/template/public/fixtures/_OMITTED.md`](./src/mjswan/template/public/fixtures/_OMITTED.md) |
| `src/mjswan/template/src/assets` | 1 | 786 KB | [`src/mjswan/template/src/assets/_OMITTED.md`](./src/mjswan/template/src/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
