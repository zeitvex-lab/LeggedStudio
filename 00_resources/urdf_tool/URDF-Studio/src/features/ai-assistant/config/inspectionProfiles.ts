export type InspectionProfileLayer = 'base' | 'format' | 'morph' | 'workflow' | 'target'

export type InspectionIssueSeverity = 'error' | 'warning' | 'suggestion'

export type InspectionEvidenceLevel = 'L1' | 'L2' | 'L3' | 'L4'

export interface InspectionProfileItem {
  id: string
  name: string
  nameZh: string
  description: string
  descriptionZh: string
  maxScore: number
  severityOnFailure: InspectionIssueSeverity
  evidenceLevelRequired?: InspectionEvidenceLevel
}

export interface InspectionProfileDefinition {
  id: string
  name: string
  nameZh: string
  layer: InspectionProfileLayer
  description: string
  descriptionZh: string
  items: InspectionProfileItem[]
}

const item = (
  id: string,
  name: string,
  nameZh: string,
  description: string,
  descriptionZh: string,
  severityOnFailure: InspectionIssueSeverity,
  evidenceLevelRequired?: InspectionEvidenceLevel,
): InspectionProfileItem => ({
  id,
  name,
  nameZh,
  description,
  descriptionZh,
  maxScore: 10,
  severityOnFailure,
  evidenceLevelRequired,
})

export const INSPECTION_PROFILE_DEFINITIONS: InspectionProfileDefinition[] = [
  {
    id: 'base.robot_model',
    name: 'Robot Model Baseline',
    nameZh: '通用机器人模型基础检查',
    layer: 'base',
    description: 'Checks the structural contract that any normalized robot model should satisfy.',
    descriptionZh: '检查任意归一化机器人模型都应满足的基础结构契约。',
    items: [
      item('model_identity', 'Model identity', '模型身份', 'The model should have a stable name and traceable import source.', '模型应有稳定名称；导入来源应可追踪。', 'warning', 'L2'),
      item('link_joint_required_fields', 'Link / joint required fields', 'Link / Joint 必填字段', 'Links and joints should have complete names; joints should include type and parent/child references.', 'link 与 joint 名称完整；joint 具备类型、父子引用。', 'error', 'L1'),
      item('reference_integrity', 'Reference integrity', '引用完整性', 'Parent/child, mesh, material, mimic, actuator, and other references should resolve.', 'parent/child、mesh、material、mimic、actuator 等引用应存在。', 'error', 'L1'),
      item('tree_connectivity', 'Tree connectivity', '树拓扑连通性', 'A normal rigid-body tree should have one root, no isolated subgraphs, and no repeated child ownership.', '普通刚体树应单根、无孤立子图、无重复 child 归属。', 'error', 'L1'),
      item('closed_loop_declaration', 'Closed-loop declaration', '闭链声明', 'Closed-loop or parallel structures should explicitly describe their representation and downstream constraints.', '闭链或并联结构应显式说明表达方式和下游约束。', 'warning', 'L3'),
    ],
  },
  {
    id: 'base.physical_plausibility',
    name: 'Physical Plausibility',
    nameZh: '通用物理合理性检查',
    layer: 'base',
    description: 'Checks mass, inertia, and physical plausibility independent of robot shape.',
    descriptionZh: '检查与机器人形态无关的质量、惯性和基础物理合理性。',
    items: [
      item('mass_positive', 'Positive mass', '质量有效性', 'All links participating in dynamics should have mass greater than zero.', '所有关联动力学的 link 质量应大于 0。', 'error', 'L1'),
      item('inertia_positive', 'Positive inertia', '惯性有效性', 'Inertia diagonal values should be positive and satisfy the triangle inequality.', '惯性矩阵对角线应大于 0，并满足三角不等式。', 'error', 'L1'),
      item('center_of_mass_reasonable', 'Reasonable center of mass', '质心合理性', 'The center of mass should be inside or near a plausible geometric range for the link.', '质心应位于或接近 link 几何体合理范围。', 'warning', 'L3'),
      item('inertia_geometry_match', 'Inertia and geometry match', '惯性与几何匹配', 'Inertia magnitude and principal directions should roughly match the geometry scale and axes.', '惯性大小和方向应与几何尺度、主轴大致匹配。', 'warning', 'L3'),
      item('repeated_part_consistency', 'Repeated part consistency', '重复部件一致性', 'Symmetric or repeated parts should keep mass, inertia, and transforms consistent.', '对称或重复部件的质量、惯性、坐标应保持一致。', 'warning', 'L3'),
    ],
  },
  {
    id: 'base.simulation_readiness',
    name: 'Simulation Readiness',
    nameZh: '通用仿真就绪检查',
    layer: 'base',
    description: 'Checks joint semantics, limits, collision simplification, and simulation stability.',
    descriptionZh: '检查关节语义、限位、碰撞体简化和基础仿真稳定性。',
    items: [
      item('joint_limits_valid', 'Valid joint limits', '关节限位有效性', 'Revolute/prismatic and similar joints should have reasonable lower, upper, effort, and velocity limits.', 'revolute/prismatic 等关节应有合理 lower/upper/effort/velocity。', 'error', 'L1'),
      item('continuous_joint_semantics', 'Continuous joint semantics', 'Continuous 语义', 'Continuous joints should not depend on position lower/upper limits.', 'continuous 关节不应依赖 position lower/upper。', 'warning', 'L2'),
      item('dynamics_parameters', 'Dynamics parameters', '动力学参数', 'Damping and friction should not be missing or obviously abnormal.', 'damping/friction 不应缺失或明显异常。', 'suggestion', 'L3'),
      item('collision_simplification', 'Collision simplification', '碰撞体简化', 'Collision geometry should prefer primitives or low-complexity meshes.', 'collision 应优先使用 primitive 或低复杂度 mesh。', 'warning', 'L3'),
      item('self_collision_risk', 'Self-collision risk', '自碰撞风险', 'The initial pose should not have obvious overlaps or unstable contact risks.', '初始姿态下不应存在明显重叠或接触不稳定风险。', 'warning', 'L3'),
    ],
  },
  {
    id: 'base.maintainability',
    name: 'Model Maintainability',
    nameZh: '模型可维护性检查',
    layer: 'base',
    description: 'Checks naming and readability conventions that make the model maintainable.',
    descriptionZh: '检查命名、可读性和后续维护相关约定。',
    items: [
      item('naming_unique', 'Unique naming', '命名唯一性', 'Link, joint, material, and asset names should be unique.', 'link、joint、material、asset 名称应唯一。', 'error', 'L1'),
      item('naming_semantic', 'Semantic naming', '命名语义化', 'Names should describe part position, function, or hierarchy.', '名称应表达部件位置、功能或层级。', 'suggestion', 'L3'),
      item('naming_style', 'Naming style', '命名风格', 'snake_case or a consistent project naming style is recommended.', '推荐 snake_case 或项目内一致风格。', 'suggestion', 'L3'),
      item('structure_readability', 'Structure readability', '结构可读性', 'Topology and naming should make parent/child relationships easy to trace.', '拓扑和命名应便于追踪父子关系。', 'suggestion', 'L3'),
      item('asset_path_stability', 'Asset path stability', '资产路径稳定性', 'Mesh, texture, and include paths should be portable and packageable.', 'mesh、texture、include 路径应可移植、可打包。', 'warning', 'L2'),
    ],
  },
  {
    id: 'morph.humanoid',
    name: 'Humanoid Morphology',
    nameZh: '人形机器人检查',
    layer: 'morph',
    description: 'Checks humanoid body hierarchy, symmetry, waist, and limb axis assumptions.',
    descriptionZh: '检查人形机器人的躯干层级、对称、腰部和肢体轴向约定。',
    items: [
      item('humanoid_body_hierarchy', 'Humanoid body hierarchy', '人形躯干层级', 'Pelvis, torso, head, arms, and legs should have a clear hierarchy.', 'pelvis/torso/head/arms/legs 层级应清晰。', 'warning', 'L3'),
      item('left_right_symmetry', 'Left/right symmetry', '左右对称', 'Left and right limbs should keep reasonable mirrored mass, inertia, length, and joint axes.', '左右肢体质量、惯性、长度、关节轴应保持合理镜像。', 'warning', 'L3'),
      item('waist_centering', 'Waist centering', '腰部中心', 'Waist or pelvis should be near the reasonable center of the left and right limbs.', 'waist/pelvis 应位于左右肢体合理中心。', 'warning', 'L3'),
      item('leg_chain_alignment', 'Leg chain alignment', '腿部链路对齐', 'Hip, knee, and ankle origins and axes should match a standing pose.', 'hip/knee/ankle 原点和轴向应符合站立姿态。', 'warning', 'L3'),
      item('arm_chain_alignment', 'Arm chain alignment', '手臂链路对齐', 'Shoulder, elbow, and wrist chains should be consistent between left and right sides.', 'shoulder/elbow/wrist 关节链应左右一致。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'morph.biped',
    name: 'Biped Morphology',
    nameZh: '双足机器人检查',
    layer: 'morph',
    description: 'Checks biped leg pairs, lower-body axes, foot contact, and standing reference pose.',
    descriptionZh: '检查双足腿部成对结构、下肢轴向、足端接触和站立参考姿态。',
    items: [
      item('biped_leg_pair', 'Biped leg pair', '双腿成对结构', 'Left and right leg topology and degrees of freedom should broadly correspond.', '左右腿拓扑和自由度应基本对应。', 'warning', 'L3'),
      item('hip_knee_ankle_axes', 'Hip/knee/ankle axes', '髋膝踝轴向', 'Hip, knee, and ankle axes should match the mechanism design.', '髋、膝、踝轴向应符合机构预期。', 'warning', 'L3'),
      item('foot_contact_geometry', 'Foot contact geometry', '足端接触几何', 'Foot collision should provide stable ground contact and avoid high-resolution mesh contact.', 'foot collision 应稳定接地，避免高精 mesh 直接接触。', 'warning', 'L3'),
      item('standing_reference_pose', 'Standing reference pose', '站立参考姿态', 'The initial pose should be explainable as stable standing or document an exception.', '初始姿态应能解释为稳定站立或明确说明例外。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'morph.quadruped',
    name: 'Quadruped Morphology',
    nameZh: '四足机器人检查',
    layer: 'morph',
    description: 'Checks quadruped leg completeness, symmetry, hip layout, chain consistency, and foot contact.',
    descriptionZh: '检查四足机器人的四腿完整性、对称、髋部布局、腿链一致性和足端接触。',
    items: [
      item('quadruped_leg_quads', 'Four-leg completeness', '四腿完整性', 'FL/FR/RL/RR or equivalent four-leg structures should be complete.', 'FL/FR/RL/RR 或等价四腿结构应完整。', 'error', 'L3'),
      item('quadruped_symmetry', 'Quadruped symmetry', '前后左右一致性', 'Symmetric legs should have reasonably corresponding mass, inertia, length, and axes.', '对称腿的质量、惯性、长度、轴向应合理对应。', 'warning', 'L3'),
      item('hip_layout', 'Hip layout', '髋部布局', 'The four hip origins should match the body coordinate system, width, and length directions.', '四个 hip 原点应与机身坐标和宽长方向一致。', 'warning', 'L3'),
      item('knee_ankle_chain', 'Knee/ankle chain', '膝/踝链路', 'Each leg should keep consistent joint ordering, axes, and limits.', '每条腿关节顺序、轴向和限位应一致。', 'warning', 'L3'),
      item('foot_contact', 'Foot contact', '足端接触', 'Foot collision should be simplified, correctly placed, and symmetric.', '足端 collision 应简化、位置正确、左右一致。', 'warning', 'L3'),
    ],
  },
  {
    id: 'morph.manipulator',
    name: 'Manipulator Morphology',
    nameZh: '机械臂检查',
    layer: 'morph',
    description: 'Checks serial arm assumptions such as chain continuity, axes, tool frame, limits, and base frame.',
    descriptionZh: '检查串联机械臂的主链连续性、关节轴、工具坐标系、限位和基座坐标。',
    items: [
      item('serial_chain_integrity', 'Serial chain integrity', '串联链完整性', 'The main chain from base to tool should be continuous and unbroken.', 'base 到 tool 的主链应连续、无断裂。', 'error', 'L3'),
      item('joint_axis_consistency', 'Joint axis consistency', '关节轴一致性', 'Joint axes should match the arm design and installation direction.', '各关节轴应符合机械臂设计和安装方向。', 'warning', 'L3'),
      item('tool_frame_presence', 'Tool frame presence', '工具坐标系', 'The model should provide a clear tool, flange, or end_effector frame.', '应有清晰 tool/flange/end_effector 表达。', 'suggestion', 'L3'),
      item('joint_limit_order', 'Joint limit order', '关节限位顺序', 'Lower and upper limits should be ordered correctly and match mechanism expectations.', 'lower/upper 应正确，范围应符合机构常识。', 'error', 'L1'),
      item('base_mounting_frame', 'Base mounting frame', '基座安装坐标', 'base_link coordinates should be clear for mounting and simulation.', 'base_link 坐标应清晰，便于安装和仿真。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'morph.mobile_base',
    name: 'Mobile Base Morphology',
    nameZh: '移动底盘检查',
    layer: 'morph',
    description: 'Checks wheeled or mobile-base coordinate conventions, wheel axes, symmetry, contact, and suspension.',
    descriptionZh: '检查轮式或移动底盘坐标约定、轮轴、对称、接地碰撞和悬挂配置。',
    items: [
      item('base_frame_convention', 'Base frame convention', '底盘坐标约定', 'base_link should have clear X-forward and Z-up conventions or documentation.', 'base_link 应有清晰 X 前、Z 上等约定或说明。', 'warning', 'L3'),
      item('wheel_joint_axes', 'Wheel joint axes', '轮关节轴向', 'Wheel joint axes should match the wheel rotation direction.', 'wheel joint axis 应与轮旋转方向一致。', 'error', 'L3'),
      item('wheel_pair_symmetry', 'Wheel pair symmetry', '轮系对称', 'Left and right wheel position, radius, and axes should match or explain differences.', '左右轮位置、半径、轴向应一致或有明确差异。', 'warning', 'L3'),
      item('ground_collision', 'Ground collision', '接地碰撞', 'Wheel, track, and base collision should be suitable for contact simulation.', '轮、履带、底盘 collision 应适合接触仿真。', 'warning', 'L3'),
      item('caster_or_suspension', 'Caster or suspension', '万向轮/悬挂', 'Caster and suspension components should have explainable joints and collision setup.', 'caster、悬挂等应有可解释的关节和碰撞配置。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'morph.gripper',
    name: 'Gripper Morphology',
    nameZh: '夹爪/末端执行器检查',
    layer: 'morph',
    description: 'Checks simple gripper finger pairing, closing direction, coupling, and contact collision.',
    descriptionZh: '检查简单夹爪的指节成对、闭合方向、联动表达和接触碰撞。',
    items: [
      item('finger_pairing', 'Finger pairing', '指节成对关系', 'Left/right or multi-finger structures should be paired clearly.', '左右或多指结构应成对清晰。', 'warning', 'L3'),
      item('closing_direction', 'Closing direction', '闭合方向', 'Finger joint axes and limits should match the closing direction.', '指节关节轴和 limit 应与闭合方向一致。', 'warning', 'L3'),
      item('mimic_or_coupling', 'Mimic or coupling', '联动表达', 'Parallel grippers should use mimic or clearly document coupling.', '平行夹爪应使用 mimic 或明确联动说明。', 'suggestion', 'L3'),
      item('contact_collision', 'Contact collision', '接触碰撞', 'Fingertip collision should be suitable for grasping contact.', '指尖 collision 应适合抓取接触。', 'warning', 'L3'),
    ],
  },
  {
    id: 'morph.dexterous_hand',
    name: 'Dexterous Hand Morphology',
    nameZh: '灵巧手检查',
    layer: 'morph',
    description: 'Checks multi-finger topology, finger limits, tendon/mimic mappings, and dense collision balance.',
    descriptionZh: '检查多指手拓扑、指关节限位、腱/联动映射和碰撞密度平衡。',
    items: [
      item('finger_topology', 'Finger topology', '多指拓扑', 'Palm-to-finger chains should be clear and complete.', 'palm 到各 finger 的链路应清晰完整。', 'error', 'L3'),
      item('finger_joint_limits', 'Finger joint limits', '指关节限位', 'Finger joint limits should match bending direction and motion range.', '指关节限位应符合弯曲方向和活动范围。', 'warning', 'L3'),
      item('tendon_or_mimic_mapping', 'Tendon or mimic mapping', '腱/联动映射', 'Tendon, mimic, or actuator relationships should be complete and traceable.', 'tendon、mimic 或 actuator 关系应完整可追踪。', 'warning', 'L3'),
      item('dense_collision_balance', 'Dense collision balance', '碰撞密度平衡', 'Fingertips may be detailed, but palm and phalanges should avoid overly complex collision.', '指尖可较细，手掌和指节不应使用过高复杂度碰撞。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'morph.parallel_mechanism',
    name: 'Parallel / Closed-Loop Mechanism',
    nameZh: '并联/闭链机构检查',
    layer: 'morph',
    description: 'Checks closed-loop representation, constraint consumers, tree approximation risk, and linkage mass distribution.',
    descriptionZh: '检查闭链表达、约束消费方、树近似风险和连杆质量归属。',
    items: [
      item('closed_loop_representation', 'Closed-loop representation', '闭链表达方式', 'The model should explain how closed loops are represented in URDF, MJCF, SDF, or USD.', '应说明闭链如何在 URDF/MJCF/SDF/USD 中表达。', 'warning', 'L3'),
      item('constraint_consumer', 'Constraint consumer', '约束消费方', 'The model should identify which simulator or controller restores closed-loop constraints.', '应说明依赖哪个仿真器或控制器恢复闭链约束。', 'warning', 'L4'),
      item('tree_approximation_risk', 'Tree approximation risk', '树近似风险', 'If a tree approximates a closed loop, lost constraints should be marked.', '若用树结构近似闭链，应标出丢失的约束。', 'warning', 'L3'),
      item('linkage_mass_distribution', 'Linkage mass distribution', '连杆质量归属', 'Parallel linkage mass and inertia should be attributed clearly.', '并联杆件质量和惯性应归属清晰。', 'warning', 'L3'),
    ],
  },
  {
    id: 'format.urdf',
    name: 'URDF Source Format',
    nameZh: 'URDF 源格式检查',
    layer: 'format',
    description: 'Checks source-format risks specific to URDF consumers and extensions.',
    descriptionZh: '检查 URDF 消费方、扩展标签和源格式契约相关风险。',
    items: [
      item('urdf_robot_root', '<robot> root', '<robot> 根节点', 'The source should have one <robot> root and a stable name.', '必须有唯一 <robot> 根节点和稳定 name。', 'error', 'L2'),
      item('urdf_link_joint_contract', 'URDF link/joint contract', 'URDF Link/Joint 契约', 'URDF link/joint required fields should be complete and references should exist.', 'link/joint 必填字段完整，引用存在。', 'error', 'L1'),
      item('urdf_tree_constraint', 'URDF tree constraint', 'URDF 树约束', 'Core URDF should not directly encode general graphs or closed loops.', '核心 URDF 不应直接表达普通图或闭环。', 'error', 'L2'),
      item('urdf_joint_semantics', 'URDF joint semantics', 'URDF 关节语义', 'fixed, continuous, revolute, prismatic, and other tags should match their semantics.', 'fixed/continuous/revolute/prismatic 等标签应符合语义。', 'warning', 'L2'),
      item('urdf_extension_compatibility', 'URDF extension compatibility', 'URDF 扩展兼容性', 'transmission, gazebo, sensor, and custom tags should document target consumers.', 'transmission、gazebo、sensor、自定义标签应说明目标消费方。', 'warning', 'L2'),
    ],
  },
  {
    id: 'format.xacro',
    name: 'Xacro Source Format',
    nameZh: 'Xacro 源格式检查',
    layer: 'format',
    description: 'Checks Xacro macros, args, includes, and expanded URDF validity.',
    descriptionZh: '检查 Xacro 的 macro、arg、include 以及展开后 URDF 的源格式风险。',
    items: [
      item('xacro_macro_contract', 'Macro contract', 'Macro 契约', 'Macro parameters, defaults, and block parameters should be clear.', 'macro 参数、默认值、block 参数应清晰。', 'warning', 'L4'),
      item('xacro_arg_property', 'Arg / property', 'Arg/Property', 'Argument names should be stable and defaults should expand successfully.', '参数命名应稳定，默认值应可展开。', 'warning', 'L4'),
      item('xacro_include_resolution', 'Include resolution', 'Include 解析', 'Include paths should resolve and be packageable.', 'include 路径应可解析和可打包。', 'error', 'L4'),
      item('xacro_expanded_urdf_validity', 'Expanded URDF validity', '展开后 URDF 有效性', 'The expanded output must satisfy the base URDF requirements.', '展开结果必须满足 format.urdf 的基础要求。', 'error', 'L2'),
      item('xacro_profile_variants', 'Variant consistency', '变体一致性', 'Different parameter branches should not generate broken models.', '不同 profile/参数分支不应生成破损模型。', 'warning', 'L4'),
    ],
  },
  {
    id: 'format.mjcf',
    name: 'MJCF Source Format',
    nameZh: 'MJCF 源格式检查',
    layer: 'format',
    description: 'Checks MJCF-specific source semantics such as bodies, joints, geoms, sites, tendons, and actuators.',
    descriptionZh: '检查 MJCF 特有的 body、joint、geom、site、tendon 和 actuator 源格式语义。',
    items: [
      item('mjcf_root_model', 'MJCF root model', 'MJCF 根模型', '<mujoco> and model names should be clear.', '<mujoco> 和 model 命名应清晰。', 'error', 'L2'),
      item('mjcf_body_joint_geom', 'Body / joint / geom', 'Body/Joint/Geom', 'body, joint, and geom hierarchy should match MuJoCo semantics.', 'body、joint、geom 层级应符合 MuJoCo 语义。', 'error', 'L2'),
      item('mjcf_site_frame_usage', 'Site / frame usage', 'Site/Frame 使用', 'Sites and frames should explain coordinates, tendon attachments, or sensor purposes.', 'site 和 frame 应能解释坐标、腱附件或传感目的。', 'warning', 'L2'),
      item('mjcf_tendon_actuator', 'Tendon / actuator', 'Tendon/Actuator', 'Tendon, actuator, limit, and gear relationships should be complete.', 'tendon、actuator、limit、gear 关系应完整。', 'warning', 'L2'),
      item('mjcf_contact_defaults', 'Contact and defaults', '接触与默认值', 'geom contact, default, and compiler settings should fit the target simulation.', 'geom contact、default、compiler 设置应适合目标仿真。', 'suggestion', 'L2'),
    ],
  },
  {
    id: 'format.sdf',
    name: 'SDF Source Format',
    nameZh: 'SDF 源格式检查',
    layer: 'format',
    description: 'Checks SDF model/world scope, frames, plugins, and joints.',
    descriptionZh: '检查 SDF 的 model/world 作用域、frame、plugin 和 joint 等源格式风险。',
    items: [
      item('sdf_root_version', 'SDF root and version', 'SDF 根节点与版本', '<sdf> should have a version and valid structure.', '<sdf> 应有 version，且结构合法。', 'error', 'L4'),
      item('sdf_model_world', 'Model / world', 'Model/World', 'The source should contain at least one model or world with stable naming.', '应至少有 model 或 world，命名稳定。', 'error', 'L4'),
      item('sdf_nested_model_frame', 'Nested model / frame', 'Nested Model/Frame', 'Nested model and frame relationships should be explicit.', 'nested model 和 frame 关系应明确。', 'warning', 'L4'),
      item('sdf_joint_semantics', 'SDF joint semantics', 'SDF Joint 语义', 'joint parent/child, pose, and axis should follow SDF semantics.', 'joint parent/child、pose、axis 应符合 SDF 语义。', 'error', 'L4'),
      item('sdf_plugin_sensor', 'Plugin / sensor', 'Plugin/Sensor', 'Plugin and sensor configuration should document the target Gazebo environment.', 'plugin 和 sensor 配置应说明目标 Gazebo 环境。', 'warning', 'L4'),
    ],
  },
  {
    id: 'format.usd',
    name: 'USD Source Format',
    nameZh: 'USD / USD Physics 检查',
    layer: 'format',
    description: 'Checks USD stage, prims, USD Physics, articulation, assets, and material bindings.',
    descriptionZh: '检查 USD 的 stage、prim、USD Physics、articulation、资源和材质绑定风险。',
    items: [
      item('usd_stage_root', 'Stage root', 'Stage 根结构', 'Stage, defaultPrim, and root prim should be clear.', 'stage、defaultPrim、root prim 应清晰。', 'warning', 'L4'),
      item('usd_physics_schema', 'USD Physics schema', 'USD Physics Schema', 'Rigid body, joint, collision, and mass schemas should be complete.', 'rigid body、joint、collision、mass schema 应完整。', 'error', 'L4'),
      item('usd_articulation_root', 'Articulation root', 'Articulation Root', 'Joint trees should have the correct articulation root when needed.', '需要关节树时应有正确 articulation root。', 'error', 'L4'),
      item('usd_asset_references', 'Asset references', '资产引用', 'Payload, reference, texture, and mesh paths should resolve.', 'payload/reference/texture/mesh 路径应可解析。', 'error', 'L4'),
      item('usd_material_binding', 'Material binding', '材质绑定', 'Visual and physics materials should be traceable.', 'visual material 与 physics material 应可追踪。', 'suggestion', 'L4'),
    ],
  },
  {
    id: 'format.mesh_asset',
    name: 'Mesh Asset',
    nameZh: 'Mesh 资产检查',
    layer: 'format',
    description: 'Checks mesh scale, orientation, normals, complexity, and bounds.',
    descriptionZh: '检查 mesh 尺度、朝向、法线、复杂度和包围盒。',
    items: [
      item('mesh_scale_units', 'Scale and units', '尺度与单位', 'Mesh scale should match robot units.', 'mesh 尺度应与机器人单位一致。', 'warning', 'L3'),
      item('mesh_orientation', 'Mesh orientation', '坐标朝向', 'Mesh axes and import pose should be reasonable.', 'mesh 坐标轴和导入姿态应合理。', 'warning', 'L3'),
      item('mesh_normals_winding', 'Normals and winding', '法线与面朝向', 'Normals, winding, and double-sided risks should be explainable.', '法线、绕序、双面风险应可解释。', 'suggestion', 'L3'),
      item('mesh_complexity', 'Mesh complexity', '面数复杂度', 'Visual meshes may be detailed, but collision should avoid high face counts.', 'visual 可高精，collision 不应直接使用过高面数 mesh。', 'warning', 'L3'),
      item('mesh_bounds', 'Mesh bounds', '包围盒', 'Bounds should match expected part dimensions.', '包围盒应与预期部件尺寸匹配。', 'warning', 'L3'),
    ],
  },
  {
    id: 'target.ros_control',
    name: 'ROS Control Compatibility',
    nameZh: 'ROS Control 兼容性检查',
    layer: 'target',
    description: 'Checks transmissions, interfaces, limits, and naming for ROS Control.',
    descriptionZh: '检查 ROS Control 的 transmission、接口、控制限位和命名映射。',
    items: [
      item('ros_control_transmission', 'Transmission', 'Transmission', 'Controlled joints should have transmission or equivalent ros2_control configuration.', '需要控制的 joint 应有 transmission 或 ros2_control 等价配置。', 'warning', 'L4'),
      item('ros_control_interface', 'Hardware interface', 'Hardware Interface', 'Command and state interfaces should match controller needs.', 'command/state interface 应与控制器需求匹配。', 'warning', 'L4'),
      item('ros_control_limits', 'Control limits', '控制限位', 'effort, velocity, and position limits should be complete.', 'effort、velocity、position limit 应完整。', 'error', 'L2'),
      item('ros_control_naming', 'Control naming', '控制命名', 'Joint names should be easy to map into controllers.', 'joint 名称应便于控制器映射。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'target.gazebo',
    name: 'Gazebo Compatibility',
    nameZh: 'Gazebo 兼容性检查',
    layer: 'target',
    description: 'Checks Gazebo extensions, contact, sensors, and inertial stability.',
    descriptionZh: '检查 Gazebo 扩展、接触配置、传感器插件和惯性稳定性。',
    items: [
      item('gazebo_extensions', 'Gazebo extensions', 'Gazebo 扩展', 'Gazebo tags or plugins should document the target version.', 'gazebo tag 或 plugin 应说明目标版本。', 'warning', 'L4'),
      item('gazebo_collision_contact', 'Collision contact', '接触配置', 'collision, surface, and friction should suit Gazebo contact simulation.', 'collision、surface、friction 应适合 Gazebo 接触。', 'warning', 'L4'),
      item('gazebo_sensor_plugins', 'Sensor plugins', '传感器插件', 'Sensor and plugin configuration should be complete and references should exist.', 'sensor/plugin 配置应完整且引用存在。', 'warning', 'L4'),
      item('gazebo_inertial_stability', 'Inertial stability', '惯性稳定性', 'Tiny mass, tiny inertia, and overlapping collision should be marked as risk.', '小质量、小惯性、重叠碰撞体应标记风险。', 'warning', 'L3'),
    ],
  },
  {
    id: 'target.mujoco',
    name: 'MuJoCo Compatibility',
    nameZh: 'MuJoCo 兼容性检查',
    layer: 'target',
    description: 'Checks MuJoCo contact, actuator mapping, tendons, and inertia policy.',
    descriptionZh: '检查 MuJoCo 接触、actuator 映射、tendon 限位和惯性策略。',
    items: [
      item('mujoco_geom_contact', 'Geom contact', 'Geom 接触', 'geom type, contype, conaffinity, and friction should be reasonable.', 'geom 类型、contype、conaffinity、friction 应合理。', 'warning', 'L4'),
      item('mujoco_actuator_mapping', 'Actuator mapping', 'Actuator 映射', 'motor, position, velocity, and tendon actuators should map to the correct joint or tendon.', 'motor、position、velocity、tendon actuator 应映射到正确 joint/tendon。', 'warning', 'L4'),
      item('mujoco_tendon_limits', 'Tendon limits', 'Tendon 限位', 'tendon range, limited, and attachment references should be complete.', 'tendon range、limited、附件引用应完整。', 'warning', 'L4'),
      item('mujoco_inertia_policy', 'Inertia policy', '惯性策略', 'inertiafromgeom or explicit inertial policy should be clear.', 'inertiafromgeom 或显式 inertial 策略应清晰。', 'suggestion', 'L4'),
    ],
  },
  {
    id: 'target.isaac_sim',
    name: 'Isaac Sim Compatibility',
    nameZh: 'Isaac Sim 兼容性检查',
    layer: 'target',
    description: 'Checks Isaac articulation, joint drives, collision API, and asset packaging.',
    descriptionZh: '检查 Isaac articulation、joint drive、collision API 和资产打包。',
    items: [
      item('isaac_articulation', 'Articulation', 'Articulation', 'articulation root and joint hierarchy should match Isaac expectations.', 'articulation root、joint 层级应符合 Isaac 预期。', 'error', 'L4'),
      item('isaac_joint_drive', 'Joint drive', 'Joint Drive', 'stiffness, damping, drive type, and limits should be complete.', 'stiffness、damping、drive type、limits 应完整。', 'warning', 'L4'),
      item('isaac_collision_api', 'Collision API', 'Collision API', 'collision approximation and physics material should be usable.', 'collision approximation、physics material 应可用。', 'warning', 'L4'),
      item('isaac_asset_package', 'Asset package', '资产打包', 'USD, mesh, and texture paths should be suitable for packaging and loading.', 'USD、mesh、texture 路径应适合打包和加载。', 'error', 'L4'),
    ],
  },
  {
    id: 'target.export_portability',
    name: 'Export Portability',
    nameZh: '跨格式导出可移植性检查',
    layer: 'target',
    description: 'Checks whether core semantics, extensions, assets, and closed-loop constraints can travel across formats.',
    descriptionZh: '检查核心语义、扩展、资产和闭链约束能否跨格式表达。',
    items: [
      item('portable_core_semantics', 'Portable core semantics', '可移植核心语义', 'link, joint, inertial, visual, and collision should be expressible across formats.', 'link/joint/inertial/visual/collision 应可跨格式表达。', 'warning', 'L3'),
      item('extension_loss_risk', 'Extension loss risk', '扩展丢失风险', 'transmission, gazebo, plugin, tendon, USD schema, and similar conversion risks should be documented.', 'transmission、gazebo、plugin、tendon、USD schema 等转换风险应说明。', 'warning', 'L4'),
      item('asset_path_portability', 'Asset path portability', '资产路径可移植', 'mesh, texture, and include paths should export and relocate correctly.', 'mesh/texture/include 路径应可导出和重定位。', 'error', 'L2'),
      item('closed_loop_export_risk', 'Closed-loop export risk', '闭链导出风险', 'Closed-loop or constraint support in the target format should be documented.', '闭链或约束在目标格式中的表达能力应说明。', 'warning', 'L4'),
    ],
  },
  {
    id: 'workflow.assembly',
    name: 'Assembly Workflow',
    nameZh: '多机器人组装检查',
    layer: 'workflow',
    description: 'Checks multi-component namespaces, roots, bridge joints, and component transforms.',
    descriptionZh: '检查多组件命名空间、根组件、桥接关节和组件变换。',
    items: [
      item('assembly_namespace', 'Assembly namespace', '命名空间', 'Multi-component links, joints, and assets should avoid duplicate names.', '多组件 link/joint/asset 应避免重名。', 'error', 'L1'),
      item('assembly_root_selection', 'Root selection', '根组件选择', 'Assembly root and primary model should be explicit.', '组装 root 和主模型应明确。', 'warning', 'L3'),
      item('bridge_joint_contract', 'Bridge joint contract', 'Bridge Joint 契约', 'Bridge joint parent/child, origin, axis, and type should be complete.', 'bridge joint parent/child、origin、axis、type 应完整。', 'error', 'L1'),
      item('component_transform', 'Component transform', '组件变换', 'Component transforms should be traceable and reflected in export.', '组件 transform 应可追踪并反映到导出。', 'warning', 'L2'),
    ],
  },
  {
    id: 'workflow.hardware_config',
    name: 'Hardware Configuration',
    nameZh: '硬件配置检查',
    layer: 'workflow',
    description: 'Checks motor selection, effort/velocity limits, armature, damping, and friction.',
    descriptionZh: '检查电机型号、力矩/速度限位、电枢惯量、阻尼和摩擦。',
    items: [
      item('motor_type_selection', 'Motor type selection', '电机型号', 'motorType or motorId should come from a known library or be explicitly custom.', 'motorType/motorId 应来自已知库或明确自定义。', 'warning', 'L3'),
      item('effort_velocity_limits', 'Effort and velocity limits', '力矩与速度限位', 'effort and velocity should match motor and mechanical hard limits.', 'effort/velocity 应符合电机和机械硬限位。', 'warning', 'L3'),
      item('armature_equivalent_inertia', 'Equivalent armature inertia', '等效电枢惯量', 'High gear ratio or low-mass mechanisms should configure armature.', '高减速比或低质量机构应配置 armature。', 'suggestion', 'L3'),
      item('damping_friction_config', 'Damping and friction', '阻尼与摩擦', 'damping and friction should be non-negative and suitable for simulation.', 'damping/friction 应非负并适合仿真。', 'suggestion', 'L2'),
    ],
  },
  {
    id: 'workflow.collision_authoring',
    name: 'Collision Authoring',
    nameZh: '碰撞体编辑检查',
    layer: 'workflow',
    description: 'Checks collision coverage, primitive preference, offsets, and count balance.',
    descriptionZh: '检查碰撞覆盖、primitive 优先、偏移和数量平衡。',
    items: [
      item('collision_coverage', 'Collision coverage', '碰撞覆盖', 'Collision should cover the main contact regions.', 'collision 应覆盖主要接触区域。', 'warning', 'L3'),
      item('collision_primitive_preference', 'Primitive preference', 'Primitive 优先', 'Prefer box, cylinder, or sphere when they can represent collision adequately.', '能用 box/cylinder/sphere 表达时优先不用高精 mesh。', 'suggestion', 'L3'),
      item('collision_offset', 'Collision offset', '碰撞偏移', 'collision origin should not visibly deviate from visual or physical geometry.', 'collision origin 不应明显偏离 visual 或实体。', 'warning', 'L3'),
      item('collision_count_balance', 'Collision count balance', '碰撞数量平衡', 'Collision body count should balance accuracy and performance.', 'collision body 数量应兼顾精度和性能。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'workflow.inertia_authoring',
    name: 'Inertia Authoring',
    nameZh: '惯性参数编辑检查',
    layer: 'workflow',
    description: 'Checks inertia tensor validity, COM overlap, principal axes, and mass traceability.',
    descriptionZh: '检查惯性张量有效性、质心与几何重叠、主轴一致性和质量分布可追踪。',
    items: [
      item('inertia_tensor_validity', 'Inertia tensor validity', '惯性张量有效性', 'The inertia matrix should be positive definite or at least satisfy basic physical constraints.', '惯性矩阵应正定或至少满足基础物理约束。', 'error', 'L1'),
      item('com_visual_overlap', 'COM and geometry overlap', '质心与几何重叠', 'COM should not be obviously outside the geometry.', 'COM 不应明显落在几何之外。', 'warning', 'L3'),
      item('principal_axis_consistency', 'Principal axis consistency', '主轴一致性', 'Inertial frame orientation should match mass-distribution principal axes.', '惯性坐标姿态应与质量分布主轴一致。', 'suggestion', 'L3'),
      item('mass_distribution_traceability', 'Mass distribution traceability', '质量分布可追踪', 'Motor, linkage, and shell mass attribution should be explainable.', '电机、连杆、外壳质量归属应可解释。', 'suggestion', 'L3'),
    ],
  },
  {
    id: 'workflow.export_preflight',
    name: 'Export Preflight',
    nameZh: '导出前检查',
    layer: 'workflow',
    description: 'Checks portability risks before exporting to downstream tools or alternate formats.',
    descriptionZh: '检查导出到下游工具或其他格式前的可移植性风险。',
    items: [
      item('export_format_capability', 'Target format capability', '目标格式能力', 'Current model features should be representable in the target format.', '当前模型特性应能被目标格式表达。', 'warning', 'L4'),
      item('export_asset_completeness', 'Export asset completeness', '导出资产完整性', 'Meshes, textures, includes, and USD layers should be packaged completely.', 'mesh、texture、include、USD layers 应完整打包。', 'error', 'L2'),
      item('export_name_stability', 'Export name stability', '导出命名稳定性', 'Exported names should remain traceable and avoid random or conflicting names.', '导出后名称应可追踪，避免随机或冲突命名。', 'warning', 'L3'),
      item('export_roundtrip_risk', 'Round-trip risk', '往返风险', 'Information that may be lost during export and re-import should be documented.', '导出再导入可能丢失的信息应说明。', 'warning', 'L4'),
    ],
  },
]

export function getInspectionProfileDefinition(profileId: string) {
  return INSPECTION_PROFILE_DEFINITIONS.find((profile) => profile.id === profileId)
}

export function getInspectionProfileItem(profileId: string, itemId: string) {
  return getInspectionProfileDefinition(profileId)?.items.find((item) => item.id === itemId)
}

export function getInspectionProfileName(profileId: string, lang: 'en' | 'zh') {
  const profile = getInspectionProfileDefinition(profileId)
  if (!profile) {
    return profileId
  }

  return lang === 'zh' ? profile.nameZh : profile.name
}

export function getInspectionProfileLayerName(layer: InspectionProfileLayer, lang: 'en' | 'zh') {
  const labels: Record<InspectionProfileLayer, { en: string; zh: string }> = {
    base: { en: 'Base', zh: '基础通用层' },
    format: { en: 'Source Format', zh: '源格式层' },
    morph: { en: 'Morphology', zh: '机器人形态层' },
    target: { en: 'Target Platform', zh: '目标平台层' },
    workflow: { en: 'Workflow', zh: '工作流层' },
  }

  return labels[layer][lang]
}

export function getAllInspectionProfileItemCount() {
  return INSPECTION_PROFILE_DEFINITIONS.reduce(
    (sum, profile) => sum + profile.items.length,
    0,
  )
}
