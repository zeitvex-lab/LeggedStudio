# LightNav-0 — 参考资源

> **来源**：`00_open/LightNav-0/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：LightNav 视觉导航（Qwen3-VL 系）
> **收录**：183 个文件 / 1.4 MB（其中推理策略/模型文件 0 个）
> **已省略**：9 个文件 / 38.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（1 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（8 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（70 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（2 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（35 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（67 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （9 个文件）
docker/  （1 个文件）
    (直接文件)/
docs/  （11 个文件）
    (直接文件)/
evt_bench/  （4 个文件）
    (直接文件)/
habitat_server/  （20 个文件）
    (直接文件)/
    configs/
    lightnav_habitat/
robot_deploy/  （60 个文件）
    (直接文件)/
    scripts/
    src/
scripts/  （5 个文件）
    (直接文件)/
src/  （43 个文件）
    lightnav/
tests/  （30 个文件）
    (直接文件)/
    cli/
    evt_bench/
    habitat/
    serving/
    viz/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 121 |
| `.md` | 19 |
| `(无扩展名)` | 11 |
| `.sh` | 7 |
| `.yaml` | 6 |
| `.xml` | 6 |
| `.cfg` | 5 |
| `.toml` | 2 |
| `.patch` | 1 |
| `.yml` | 1 |
| `.txt` | 1 |
| `.js` | 1 |
| `.html` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
.dockerignore
.gitignore
AGENTS.md
Dockerfile
LICENSE
Makefile
README.md
THIRD_PARTY_NOTICES.md
docker/entrypoint.sh
docs/CONFIGURATION.md
docs/DEPLOYMENT.md
docs/DEVELOPMENT.md
docs/EVAL_EVT_BENCH.md
docs/EVAL_HABITAT.md
docs/GETTING_STARTED.md
docs/HABITAT_SERVER.md
docs/JETSON_THOR.md
docs/JETSON_THOR.zh.md
docs/PROTOCOL.md
docs/VISUALIZATION.md
evt_bench/README.md
evt_bench/patch_task_config.py
evt_bench/run_py.patch
evt_bench/trackvla_client_agent.py
habitat_server/configs/objectnav_hm3d_v1.yaml
habitat_server/configs/objectnav_hm3d_v2.yaml
habitat_server/configs/objectnav_mp3d.yaml
habitat_server/configs/objectnav_ovon.yaml
habitat_server/configs/vlnce_r2r.yaml
habitat_server/configs/vlnce_rxr.yaml
habitat_server/environment.yml
habitat_server/lightnav_habitat/__init__.py
habitat_server/lightnav_habitat/base.py
habitat_server/lightnav_habitat/constants.py
habitat_server/lightnav_habitat/objectnav.py
habitat_server/lightnav_habitat/objectnav_extensions/__init__.py
habitat_server/lightnav_habitat/objectnav_extensions/objectnav_dataset.py
habitat_server/lightnav_habitat/remote_server.py
habitat_server/lightnav_habitat/serve.py
habitat_server/lightnav_habitat/vlnce.py
habitat_server/lightnav_habitat/vlnce_extensions/__init__.py
habitat_server/lightnav_habitat/vlnce_extensions/vlnce_dataset.py
habitat_server/lightnav_habitat/vlnce_extensions/vlnce_measures.py
habitat_server/pyproject.toml
pyproject.toml
robot_deploy/.gitignore
robot_deploy/README.md
robot_deploy/scripts/build.sh
robot_deploy/src/robot_adapters/go2_adapter/README.md
robot_deploy/src/robot_adapters/go2_adapter/go2_adapter/__init__.py
robot_deploy/src/robot_adapters/go2_adapter/go2_adapter/adapter_node.py
robot_deploy/src/robot_adapters/go2_adapter/go2_adapter/safety.py
robot_deploy/src/robot_adapters/go2_adapter/go2_adapter/unitree_client.py
robot_deploy/src/robot_adapters/go2_adapter/package.xml
robot_deploy/src/robot_adapters/go2_adapter/resource/go2_adapter
robot_deploy/src/robot_adapters/go2_adapter/setup.cfg
robot_deploy/src/robot_adapters/go2_adapter/setup.py
robot_deploy/src/robot_adapters/go2_adapter/test/test_safety.py
robot_deploy/src/robot_adapters/go2_adapter/test/test_unitree_client.py
robot_deploy/src/robot_adapters/tron_adapter/package.xml
robot_deploy/src/robot_adapters/tron_adapter/resource/tron_adapter
robot_deploy/src/robot_adapters/tron_adapter/setup.cfg
robot_deploy/src/robot_adapters/tron_adapter/setup.py
robot_deploy/src/robot_adapters/tron_adapter/test/test_safety.py
robot_deploy/src/robot_adapters/tron_adapter/tron_adapter/__init__.py
robot_deploy/src/robot_adapters/tron_adapter/tron_adapter/adapter_node.py
robot_deploy/src/robot_adapters/tron_adapter/tron_adapter/safety.py
robot_deploy/src/vln_bringup/CMakeLists.txt
robot_deploy/src/vln_bringup/launch/go2.launch.py
robot_deploy/src/vln_bringup/launch/tron.launch.py
robot_deploy/src/vln_bringup/package.xml
robot_deploy/src/vln_client/README.md
robot_deploy/src/vln_client/package.xml
robot_deploy/src/vln_client/resource/vln_client
robot_deploy/src/vln_client/setup.cfg
robot_deploy/src/vln_client/setup.py
robot_deploy/src/vln_client/test/test_vln_client.py
robot_deploy/src/vln_client/vln_client/__init__.py
robot_deploy/src/vln_client/vln_client/vln_client.py
robot_deploy/src/vln_client/vln_client/vln_node.py
robot_deploy/src/vln_mpc/README.md
robot_deploy/src/vln_mpc/package.xml
robot_deploy/src/vln_mpc/resource/vln_mpc
robot_deploy/src/vln_mpc/setup.cfg
robot_deploy/src/vln_mpc/setup.py
robot_deploy/src/vln_mpc/test/test_geometry.py
robot_deploy/src/vln_mpc/test/test_mpc.py
robot_deploy/src/vln_mpc/test/test_mpc_node.py
robot_deploy/src/vln_mpc/vln_mpc/__init__.py
robot_deploy/src/vln_mpc/vln_mpc/geometry.py
robot_deploy/src/vln_mpc/vln_mpc/mpc.py
robot_deploy/src/vln_mpc/vln_mpc/mpc_node.py
robot_deploy/src/vln_web/package.xml
robot_deploy/src/vln_web/resource/vln_web
robot_deploy/src/vln_web/setup.cfg
robot_deploy/src/vln_web/setup.py
robot_deploy/src/vln_web/test/test_web_server.py
robot_deploy/src/vln_web/test/test_wifi.py
robot_deploy/src/vln_web/vln_web/__init__.py
robot_deploy/src/vln_web/vln_web/web_node.py
robot_deploy/src/vln_web/vln_web/web_server.py
robot_deploy/src/vln_web/vln_web/wifi.py
robot_deploy/src/vln_web/web/app.js
robot_deploy/src/vln_web/web/index.html
robot_deploy/src/vln_web/web/styles.css
scripts/eval_evt_bench.sh
scripts/eval_habitat.sh
scripts/serve_thor.sh
scripts/smoke_gpu.sh
scripts/start_servers.sh
src/lightnav/__init__.py
src/lightnav/cli/__init__.py
src/lightnav/cli/eval_habitat.py
src/lightnav/cli/eval_merge.py
src/lightnav/cli/predict.py
src/lightnav/cli/render.py
src/lightnav/cli/ws_client.py
src/lightnav/data_processor.py
src/lightnav/eval_config.py
src/lightnav/habitat/__init__.py
src/lightnav/habitat/merge.py
src/lightnav/habitat/policy.py
src/lightnav/habitat/remote_env.py
src/lightnav/habitat/results.py
src/lightnav/habitat/runner.py
src/lightnav/inference/__init__.py
src/lightnav/inference/config.py
src/lightnav/inference/engine.py
src/lightnav/inference/frame_preprocessing.py
src/lightnav/inference/model.py
src/lightnav/inference/policies.py
src/lightnav/inference/samples.py
src/lightnav/inference/vit_cache.py
src/lightnav/inference/vllm_utils.py
src/lightnav/processing.py
src/lightnav/prompts.py
src/lightnav/serving/__init__.py
src/lightnav/serving/batcher.py
src/lightnav/serving/protocol.py
src/lightnav/serving/token_budget.py
src/lightnav/serving/tracking_service.py
src/lightnav/serving/ws_server.py
src/lightnav/slowfast.py
src/lightnav/tracking.py
src/lightnav/traj_vocab.py
src/lightnav/velocity.py
src/lightnav/viz/__init__.py
src/lightnav/viz/projection.py
src/lightnav/viz/recorder.py
src/lightnav/viz/render.py
src/lightnav/viz/render_episode.py
src/lightnav/viz/video.py
src/lightnav/vln_utils.py
tests/cli/test_console_scripts.py
tests/cli/test_ws_client_payload.py
tests/conftest.py
tests/evt_bench/test_client_parse.py
tests/habitat/test_merge.py
tests/habitat/test_policy.py
tests/habitat/test_remote_env.py
tests/habitat/test_runner.py
tests/serving/test_protocol.py
tests/serving/test_token_budget.py
tests/serving/test_ws_server.py
tests/test_aspect_mode.py
tests/test_batcher.py
tests/test_ckpt_generation_compat.py
tests/test_data_processor_selective.py
tests/test_decoder_resolution.py
tests/test_fp8_quant.py
tests/test_frame_preprocessing.py
tests/test_policies.py
tests/test_prompt_dict.py
tests/test_samples.py
tests/test_slowfast.py
tests/test_tracking_decode.py
tests/test_tracking_service.py
tests/test_traj_vocab.py
tests/test_velocity.py
tests/test_vit_cache.py
tests/viz/test_recorder.py
tests/viz/test_render.py
tests/viz/test_render_episode.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `docs/assets` | 9 | 38.1 MB | [`docs/assets/_OMITTED.md`](./docs/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
