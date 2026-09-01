# Phase 1 具体功能实施计划

基于实际项目：
- `lain_job/RoboLab` — 契约体系、工作流编排
- `mjlab_new/mjlab` — 训练后端
- `rc_old/RC_WheelLeg/05_software/train/rc_mjlab` — 部署契约参考

---

## 🎯 MVP 核心纵向切片（Go2 主线）

### 任务 1：Robot Contract 统一 ⭐⭐⭐
**参考**：
- RoboLab `src/robolab/core/contracts.py`
- RC_WheelLeg `deployment_contract.yaml`
- 项目愿景第六章

**实施**：

#### 1.1 定义 Robot Contract Schema
**文件**：`contracts/robot_contract_v2.py`

```python
# 基于 RoboLab TensorContract + RC_WheelLeg 部署契约
class RobotContractV2(BaseModel):
    schema_version: str = "robot-contract-2.0"
    robot_id: str  # Go2
    family: str  # Unitree Go2
    
    # URDF 信息
    urdf_path: str
    urdf_hash: str  # SHA-256
    
    # 关节配置（明确命名）
    actuated_joints: List[str]  # 12 个腿关节
    passive_joints: List[str] = []  # 轮足的轮子
    joint_order: List[str]  # 观测/动作顺序
    
    # 控制参数
    control_hz: int = 50
    physics_hz: int = 1000
    
    # 观测/动作维度（版本化）
    observation_dim: int  # 例如 61D
    action_dim: int  # 例如 12D
    
    # Normalizer（跟随 Artifact）
    obs_normalizer: Optional[dict] = None
    action_scale: float = 1.0
    
    # 默认站姿
    default_pose: List[float]
    
    # 质量属性（来源标记）
    total_mass_kg: float
    mass_source: str  # "urdf_inertial" / "mesh_computed" / "manual"
    
    # 部署映射
    deployment_mapping: Optional[dict] = None
```

---

#### 1.2 Contract 验证工具
**文件**：`contracts/validator.py`

```python
def validate_contract(contract: RobotContractV2) -> ValidationResult:
    """验证 Contract 完整性"""
    errors = []
    
    # 检查 URDF 存在
    if not Path(contract.urdf_path).exists():
        errors.append(f"URDF not found: {contract.urdf_path}")
    
    # 检查关节数量
    if len(contract.actuated_joints) != contract.action_dim:
        errors.append(f"Joint count mismatch")
    
    # 检查 joint_order
    if len(contract.joint_order) != contract.action_dim:
        errors.append(f"Joint order mismatch")
    
    return ValidationResult(valid=len(errors)==0, errors=errors)
```

---

### 任务 2：MJLab Adapter 集成 ⭐⭐⭐
**参考**：
- `mjlab_new/mjlab` — 新版 MJLab
- `rc_old/RC_WheelLeg/05_software/train/rc_mjlab` — RC 的 MJLab 集成

**实施**：

#### 2.1 MJLab 训练适配器
**文件**：`adapters/mjlab_new/training_adapter.py`

```python
class MJLabTrainingAdapter:
    """基于 mjlab_new 的训练适配器"""
    
    def __init__(self, contract: RobotContractV2):
        self.contract = contract
        self.env = None
        
    def create_env(self, task_config: dict):
        """创建训练环境"""
        # 基于 Contract 创建环境
        # 使用 mjlab 的环境创建逻辑
        pass
    
    def train(self, epochs: int, callback=None):
        """执行训练"""
        # 训练循环
        # 实时回调更新进度
        pass
    
    def export_onnx(self, model_path: str, output_path: str):
        """导出 ONNX"""
        # PyTorch → ONNX
        # 数值验证
        pass
```

---

#### 2.2 进程隔离启动器
**文件**：`adapters/mjlab_new/launcher.py`

```python
def launch_training(
    contract_path: str,
    task_config: dict,
    output_dir: str
) -> subprocess.Popen:
    """
    独立进程启动训练
    基于 RoboLab 的进程 supervisor 模式
    """
    mjlab_venv = Path("adapters/mjlab_new/.venv")
    python_exe = mjlab_venv / "Scripts" / "python.exe"
    
    cmd = [
        str(python_exe),
        "adapters/mjlab_new/train_worker.py",
        "--contract", contract_path,
        "--config", json.dumps(task_config),
        "--output", output_dir
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_root
    )
    
    return process
```

---

### 任务 3：ONNX 导出与验证 ⭐⭐⭐
**参考**：
- Microduck RL normalizer
- RC_WheelLeg ONNX 导出
- 参考清单第七章

**实施**：

#### 3.1 ONNX 导出器
**文件**：`adapters/mjlab_new/onnx_exporter.py`

```python
import torch
import onnx
import onnxruntime as ort

class ONNXExporter:
    """基于 Microduck 经验的 ONNX 导出"""
    
    def export(
        self,
        model: torch.nn.Module,
        dummy_input: torch.Tensor,
        output_path: str,
        opset_version: int = 17
    ) -> ExportResult:
        """导出 ONNX 模型"""
        
        # 1. 导出
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            export_params=True,
            opset_version=opset_version,
            do_constant_folding=True,
            input_names=['observation'],
            output_names=['action'],
            dynamic_axes={
                'observation': {0: 'batch_size'},
                'action': {0: 'batch_size'}
            }
        )
        
        # 2. 验证模型
        onnx_model = onnx.load(output_path)
        onnx.checker.check_model(onnx_model)
        
        # 3. 数值一致性测试
        torch_output = model(dummy_input).detach().numpy()
        
        ort_session = ort.InferenceSession(output_path)
        ort_output = ort_session.run(
            None,
            {'observation': dummy_input.numpy()}
        )[0]
        
        diff = np.abs(torch_output - ort_output).max()
        
        return ExportResult(
            success=diff < 1e-5,
            output_path=output_path,
            max_diff=diff
        )
```

---

### 任务 4：Policy Artifact 标准 ⭐⭐
**参考**：
- RoboLab Artifact
- Microduck layout revision

**实施**：

#### 4.1 Policy Artifact Schema
**文件**：`contracts/policy_artifact.py`

```python
class PolicyArtifact(BaseModel):
    """训练产物的完整记录"""
    
    artifact_id: str
    created_at: datetime
    
    # 输入契约
    robot_contract: RobotContractV2
    robot_contract_hash: str  # SHA-256
    
    # 训练配置
    task_config: dict
    algorithm: str  # "PPO" / "SAC" / "TD3"
    
    # 训练结果
    training_iterations: int
    success_rate: float
    avg_reward: float
    
    # 模型文件
    pytorch_model: str  # model.pt
    onnx_model: str  # model.onnx
    model_hash: str  # SHA-256
    
    # Normalizer（必须固化）
    obs_mean: List[float]
    obs_std: List[float]
    
    # 环境版本
    mjlab_version: str
    python_version: str
    pytorch_version: str
    
    # 验证报告
    onnx_validation: dict
    sim2sim_result: Optional[dict] = None
```

---

### 任务 5：训练管理 API ⭐⭐⭐

#### 5.1 训练管理端点
**文件**：`backend/training_manager.py`

```python
# 训练任务管理器
class TrainingManager:
    def __init__(self):
        self.tasks = {}  # task_id -> TrainingTask
        
    def create_task(
        self,
        contract: RobotContractV2,
        task_config: dict
    ) -> str:
        """创建训练任务"""
        task_id = generate_id()
        
        # 启动独立进程
        process = launch_training(
            contract_path=save_contract(contract),
            task_config=task_config,
            output_dir=f"outputs/{task_id}"
        )
        
        task = TrainingTask(
            task_id=task_id,
            contract=contract,
            process=process,
            status="running"
        )
        
        self.tasks[task_id] = task
        return task_id
    
    def get_status(self, task_id: str) -> dict:
        """获取任务状态"""
        task = self.tasks[task_id]
        return {
            "task_id": task_id,
            "status": task.status,
            "progress": task.progress,
            "metrics": task.latest_metrics
        }
```

#### 5.2 API 端点
**文件**：`backend/training_api.py`

```python
@app.post("/api/training/create")
async def create_training(request: TrainingRequest):
    """创建训练任务"""
    task_id = training_manager.create_task(
        contract=request.contract,
        task_config=request.config
    )
    return {"task_id": task_id}

@app.get("/api/training/{task_id}/status")
async def get_training_status(task_id: str):
    """获取训练状态"""
    return training_manager.get_status(task_id)

@app.post("/api/training/{task_id}/stop")
async def stop_training(task_id: str):
    """停止训练"""
    training_manager.stop_task(task_id)
    return {"success": True}
```

---

## 📅 实施时间表

### Week 1（Day 1-7）
- [x] 新版控制台完成 ✅
- [ ] Robot Contract V2 实现
- [ ] Contract 验证工具
- [ ] MJLab Adapter 基础

### Week 2（Day 8-14）
- [ ] MJLab 训练集成
- [ ] ONNX 导出实现
- [ ] Policy Artifact 标准
- [ ] 训练管理 API

### Week 3（Day 15-21）
- [ ] 预训练 Go2 模型
- [ ] Sim2Sim 验证
- [ ] 训练监控界面
- [ ] WebSocket 实时更新

### Week 4（Day 22-28）
- [ ] 便携打包
- [ ] Go2 完整纵向切片测试
- [ ] 文档完善

---

## 🎯 MVP 验收标准

基于参考清单 8.3：

- [ ] 离线安装，无需系统 Python/CUDA
- [ ] 同一 Go2 Contract 被所有模块共享
- [ ] 64 env × 5 iteration smoke 自动化
- [ ] 进程无残留
- [ ] Artifact 完整记录（hash/version/config）
- [ ] 部署包生成（不自动上机）

---

**开始实施！优先级：Contract V2 → MJLab Adapter → ONNX 导出** 🚀
