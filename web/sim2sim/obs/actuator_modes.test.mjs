// `actuator_modes.js` —— 执行器角色/控制模式解析（单一真值）的回归锁。
//
// 这一层为什么值得单独钉：它是"浏览器运行时"与"同状态对拍工具"**共用**的那段规则，
// 2026-09-22 工具里少喂了这份输入（`controlModes` 写死全 "position"），于是 m20/b2w
// 两条 `go2w_rl_sdk_57` 被**误报**"两份实现不一致"（Δ=5.000e-02 = 轮位该清零却给了
// rel×scale）。**报红的方向正好是"工具自己错"** ⇒ 必须有一条测试直接钉解析语义，
// 而不是只靠端到端对拍（端到端红了会先让人怀疑实现）。
import assert from 'node:assert/strict';
import { normalizeNameMap, jointGroup, resolveActuatorRolesAndModes } from './actuator_modes.js';

let passed = 0;
function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  ok  ${name}`);
  } catch (error) {
    console.error(`  FAIL ${name}\n    ${error.message}`);
    process.exitCode = 1;
  }
}

const WHEELS = ['FR_wheel_joint', 'FL_wheel_joint', 'RR_wheel_joint', 'RL_wheel_joint'];
const LEGS12 = Array.from({ length: 12 }, (_, i) => `FR_leg${i}_joint`);

test('normalizeNameMap 把键统一小写（跨包大小写不一致）', () => {
  assert.deepEqual(normalizeNameMap({ FR_Wheel_Joint: 'velocity' }), { fr_wheel_joint: 'velocity' });
  assert.deepEqual(normalizeNameMap(null), {});
  assert.deepEqual(normalizeNameMap('nope'), {});
});

test('jointGroup 按名字推断角色（wheel/foot ⇒ wheel）', () => {
  assert.equal(jointGroup('FR_wheel_joint'), 'wheel');
  assert.equal(jointGroup('left_foot_link'), 'wheel');
  assert.equal(jointGroup('FL_calf_joint'), 'calf');
  assert.equal(jointGroup('FL_thigh_joint'), 'thigh');
  assert.equal(jointGroup('FL_hip_joint'), 'hip');
});

test('go2w 形态：机器人级 role 声明 {"wheel":"velocity"} ⇒ 4 个轮子 velocity', () => {
  const { roles, modes } = resolveActuatorRolesAndModes({
    actionDim: 16,
    jointOrder: [...LEGS12, ...WHEELS],
    jointGroup,
    robotModes: { wheel: 'velocity', FR_wheel_joint: 'velocity' },
  });
  assert.deepEqual(roles.slice(12), ['wheel', 'wheel', 'wheel', 'wheel']);
  assert.deepEqual(modes.slice(0, 12), new Array(12).fill('position'));
  assert.deepEqual(modes.slice(12), new Array(4).fill('velocity'));
});

test('m20/b2w 形态：**逐关节**点名 control_modes 同样解出 velocity（工具曾漏读）', () => {
  const wheels = ['fl_wheel_joint', 'fr_wheel_joint', 'hl_wheel_joint', 'hr_wheel_joint'];
  const { roles, modes } = resolveActuatorRolesAndModes({
    actionDim: 16,
    jointOrder: [...LEGS12, ...wheels],
    jointGroup,
    // 注意：没有 "wheel" 角色键，只有逐关节名 —— 这正是 m20 的真值形状
    robotModes: { fl_wheel_joint: 'velocity', fr_wheel_joint: 'velocity', hl_wheel_joint: 'velocity', hr_wheel_joint: 'velocity' },
  });
  assert.deepEqual(modes.slice(12), new Array(4).fill('velocity'));
});

test('优先级：策略契约 > 机器人 control；名 > 角色', () => {
  const { modes } = resolveActuatorRolesAndModes({
    actionDim: 16,
    jointOrder: [...LEGS12, ...WHEELS],
    jointGroup,
    contractModes: { fr_wheel_joint: 'position' },        // 逐名覆盖
    robotModes: { wheel: 'velocity' },                     // 角色兜底
  });
  assert.equal(modes[12], 'position');                     // FR：策略逐名赢
  assert.equal(modes[13], 'velocity');                     // FL：落到机器人角色
});

test('无任何声明：轮角色兜底 velocity，其余 position', () => {
  const { modes } = resolveActuatorRolesAndModes({
    actionDim: 16, jointOrder: [...LEGS12, ...WHEELS], jointGroup,
  });
  assert.deepEqual(modes.slice(0, 12), new Array(12).fill('position'));
  assert.deepEqual(modes.slice(12), new Array(4).fill('velocity'));
});

test('契约 actuator_roles 优先于名字推断（非轮关节归 defaultRole，不是 jointGroup 细分）', () => {
  const { roles } = resolveActuatorRolesAndModes({
    actionDim: 3,
    jointOrder: ['FR_wheel_joint', 'FL_hip_joint', 'FL_calf_joint'],
    jointGroup,
    contractRoles: { fr_wheel_joint: 'leg' },              // 契约说了算（覆盖轮子推断）
  });
  // `jointGroup` 只用来看"是不是轮"；非轮一律落 defaultRole（缺省 leg）——
  // 与 app.js 原实现逐字一致（hip/calf/thigh 不各自成角色）。
  assert.deepEqual(roles, ['leg', 'leg', 'leg']);
});

test('非法模式名 fail-safe 落 position（不抛：拼错一个词不该起不来）', () => {
  const { modes } = resolveActuatorRolesAndModes({
    actionDim: 1, jointOrder: ['x_joint'], jointGroup, contractModes: { x_joint: 'VELOCITYY' },
  });
  assert.deepEqual(modes, ['position']);
});

test('默认角色可改（非腿式机体不需要 "leg" 兜底）', () => {
  const { roles } = resolveActuatorRolesAndModes({
    actionDim: 1, jointOrder: ['palm_joint'], jointGroup, defaultRole: 'finger',
  });
  assert.deepEqual(roles, ['finger']);
});

console.log(`actuator_modes.test.mjs: ${passed} 项通过${process.exitCode ? '（有失败）' : ''}`);
