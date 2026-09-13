/**
 * Robot Contract v3 TypeScript types.
 *
 * 真值源：contracts/schema/robot-contract-3.0.schema.json
 * 与 contracts/generated/robot_contract_v3.py（Python 侧）逐字段对齐，
 * 再生成：python tools/generate_contract_models.py（json-schema-to-typescript）。
 * parity 由 contracts/tests/test_role_resolver_v3.py 守护。
 */

export type RobotId = string; // ^[a-z0-9][a-z0-9_-]*$：允许 snake_case(unitree_go2) 与连字符(zex-w)

export type RoleName = string; // ^[a-z][a-z0-9_]*$
export type LegId = string; // ^[A-Za-z0-9]+$

/** $defs/morphology：Layer 1 构型——代码唯一允许分支的维度。 */
export interface MorphologySpec {
  id: string; // quadruped_12dof / wheel_leg_16dof / biped / humanoid / hand
  legs: number; // 0..8
  leg_pattern: RoleName[];
  /** 支持 {LR}（腿 ID）与 {role}（角色）占位符，如 '{LR}_{role}_joint' */
  leg_naming: string;
  leg_ids?: LegId[];
  actuated_via?: string;
  extra_roles?: RoleName[];
  /** B4 构型级执行器范式；角色级细则见 actuator_profile.by_role[].mode */
  actuator_type?: "position" | "velocity" | "hybrid" | "bam";
  /** B4 足端形态；非腿式（morphology.id=hand）不声明 */
  foot_type?: "point" | "sole" | "wheel";
  /** B4 action.joint_order 中轮关节下标；无轮为 []，含 wheel 角色时必填非空 */
  wheel_indices?: number[];
  /** B4 质量/惯量来源口径（与 urdf.total_mass_kg 对账用） */
  mass_source?: "mjcf_compiled" | "urdf_inertial";
}

/** Layer 3 条目：名字 + 归属 + 角色，不携带数值。 */
export interface JointEntryV3 {
  name: string;
  leg?: LegId | null;
  role: RoleName;
}

export interface PassiveJointV3 {
  name: string;
  role?: RoleName;
  note?: string;
}

export interface JointsSpecV3 {
  actuated: JointEntryV3[];
  passive?: PassiveJointV3[];
  default_pose?: number[];
  joint_limits?: Record<string, { lower?: number; upper?: number; effort?: number; velocity?: number }>;
}

/** $defs/tnCurvePoint：T-N 曲线折线采样点（关节输出侧，不折算减速比）。 */
export interface TnCurvePointV3 {
  rpm: number;
  /** 该转速下可输出的峰值扭矩（Nm） */
  torque_nm: number;
}

/** $defs/actuatorParams：执行器参数（default < by_role < by_joint 三级合并）。 */
export interface ActuatorParamsV3 {
  stiffness?: number;
  damping?: number;
  effort?: number;
  velocity_limit?: number;
  armature?: number;
  friction_loss?: number;
  /** wheel 角色常用 velocity（报告 6 §4.3） */
  mode?: "position" | "velocity" | "torque";
  action_scale?: number;
  /** T-N 曲线（转矩-转速曲线）折线（rpm 升序、扭矩非增）。声明 ≠ 生效：仅 control.actuator_model="dc_motor" 时消费 */
  t_n_curve?: TnCurvePointV3[];
}

export interface ActuatorProfileV3 {
  default?: ActuatorParamsV3;
  /** ★★ 按角色声明：同构机器人共享一份（1000frames control_defaults 证据形态） */
  by_role: Record<RoleName, ActuatorParamsV3>;
  /** 异例逐关节覆盖，最好永远为空 */
  by_joint?: Record<string, ActuatorParamsV3>;
}

export interface ActionSpecV3 {
  dimension?: number; // == joint_order.length
  joint_order: string[];
  /** ★ 一等字段：模型序→契约序置换（null=恒等；M20 joint_ids_map 制度化） */
  reindex_from_model?: number[] | null;
  action_scale?: number;
  action_clip?: [number, number];
}

export interface ObservationComponentV3 {
  name: string;
  width: number; // >=1
  /** 观测缩放；缺省 = 1.0（由训练配置校准） */
  scale?: number;
  source: "imu" | "cmd" | "actuated" | "action" | "world" | "external";
  /** 角度量是否 wrap（轮关节必须 false——替代双处同步的 mask 特判） */
  wrap?: boolean;
}

export interface ObservationSpecV3 {
  /** 观测模板 ID（如 legged_base_v1） */
  kind?: string;
  /** 空数组 = 宽度声明待补全（v2 迁移的 history/视觉类观测） */
  components: ObservationComponentV3[];
  /** 0 = 未声明；components 非空时必须 == Σ width */
  dimension: number;
  normalizer?: { mean?: number[]; std?: number[] };
  /** PolicyContract 字段级表述收敛：观测历史帧数（1=无历史） */
  history_length?: number;
  /** 历史帧排布顺序 */
  history_order?: "oldest_to_newest" | "newest_to_oldest";
  /** 无历史帧时重置方式 */
  history_reset?: "zero" | "repeat";
  /** PolicyContract 字段级表述收敛：条件观测字段（AMP/模仿类附加观测） */
  conditional_fields?: ObservationComponentV3[];
  /** PolicyContract 字段级表述收敛：循环策略状态形状（与 conditional_fields 互斥） */
  recurrent_state?: {
    layers: number;
    hidden_width: number;
  };
}

export interface ControlSpecV3 {
  control_hz?: number; // 10..1000
  physics_hz?: number; // 100..10000
  decimation?: number;
  /** P1 开关：缺省 = ideal_pd（现役行为不变）；dc_motor 才消费 actuator_profile[].t_n_curve */
  actuator_model?: "ideal_pd" | "dc_motor";
}

/** $defs/taskRequirements：任务/算法包的对称需求声明（预埋，T6.1 启用三谓词匹配）。 */
export interface TaskRequirements {
  requires_morphology?: string[];
  requires_roles?: RoleName[];
  observation_template?: string;
  action_role_order?: RoleName[];
  min_obs_dimension?: number;
}

export interface RobotContractV3 {
  schema_version: "robot-contract-3.0";
  contract_id?: string; // ^[a-z0-9_-]+$
  robot_id: RobotId;
  family?: string;
  morphology: MorphologySpec;
  joints: JointsSpecV3;
  actuator_profile: ActuatorProfileV3;
  action: ActionSpecV3;
  observation: ObservationSpecV3;
  control?: ControlSpecV3;
  default_pose?: number[];
  size_class?: "S" | "M" | "L";
  locomotion_type?: "P" | "W" | "B" | "H"; // 点足/轮足/双足/人形（现存数据实况）
  urdf?: Record<string, unknown>;
  deployment?: Record<string, unknown>;
  description?: string;
  tags?: string[];
  source?: string;
  created_at?: string;
  evidence?: Record<string, unknown>[];
}
