// `onnx_slots` 槽表解析的单测（`node web/sim2sim/obs/onnx_slots.test.mjs`）。
//
// 这里钉的是 mjswan 那类**导出器命名不可依赖**的产物：名字毫无语义（`l_kwargs_policy_` /
// `l__args___0_module_1_1`），唯一真值是"第几个输入/输出" ⇒ 解析必须**按位置**，且对
// "声明与网络不符"**fail-closed**（多一路少一路都抛，不猜不改）。样例张量名逐字取自实测：
// 见 `00_know/05_任务清单.md` §P-1 的 2026-09-22 侦察条。
import assert from 'node:assert/strict';
import { resolveOnnxSlots, SLOT_KINDS } from './onnx_slots.js';

const ROBUST_IN = ['l_kwargs_policy_', 'arg1', 'l_kwargs_adapt_hx_', 'l_kwargs_command_'];
const ROBUST_OUT = [
  'l__args___0_module_0_1', 'l__args___0_module_1_1_1', 'l__args___0_module_1_1_2',
  'l__args___0_module_1_1_3', 'l__args___0_module_1_1', 'l__args___0_module_1_1_4',
  'l__args___0_module_1_1_5', 'l__args___0_module_1_1_6', 'l__args___0_module_1_1_7',
  'l__args___0_module_1_1_8', 'l__args___0_module_1_1_6', 'l__args___0_module_1_1_9',
  'l__args___0_module_1_1_10', 'l__args___0_module_1_1_11', 'l__args___0_module_1_1_12',
];
const ROBUST_CONTRACT = {
  onnx_slots: { inputs: ['actor', 'is_init', 'adapt_hx', 'command_'], outputs: { action: 10, recurrent: 4 } },
};

// 1) robust/vanilla：按位置绑定（**名字一个字都不看**）
{
  const r = resolveOnnxSlots(ROBUST_CONTRACT, ROBUST_IN, ROBUST_OUT);
  assert.equal(r.actorName, 'l_kwargs_policy_');
  assert.equal(r.isInitName, 'arg1');
  assert.equal(r.recurrentName, 'l_kwargs_adapt_hx_');
  assert.equal(r.commandName, 'l_kwargs_command_');
  assert.equal(r.actionName, ROBUST_OUT[10]);
  assert.equal(r.recurrentOutputName, ROBUST_OUT[4]);
  console.log('OK mjswan robust/vanilla：四路输入 + action/recurrent 按位置绑定');
}

// 2) facet：**同一个 onnx 家族的另一种槽序**（command 在最前）——位置映射必须跟着变
{
  const ins = ['l_kwargs_command_', 'l_kwargs_policy_', 'arg2', 'l_kwargs_adapt_hx_'];
  const r = resolveOnnxSlots(
    { onnx_slots: { inputs: ['command_', 'actor', 'is_init', 'adapt_hx'], outputs: { action: 11, recurrent: 5 } } },
    ins, ROBUST_OUT,
  );
  assert.equal(r.actorName, 'l_kwargs_policy_');
  assert.equal(r.commandName, 'l_kwargs_command_');
  assert.equal(r.isInitName, 'arg2');
  assert.equal(r.recurrentName, 'l_kwargs_adapt_hx_');
  assert.equal(r.recurrentOutputName, ROBUST_OUT[5]);
  console.log('OK mjswan facet：槽序不同也按位置绑定');
}

// 3) **没声明**槽表 ⇒ null（绝大多数策略走名字约定路径，行为不变）；但**半声明**（空对象 /
//    只有 outputs）⇒ 抛：那种状态若静默回落到名字约定，mjswan 这类图就会被**错喂**（喂的是
//    名字约定猜出来的布局），正是本模块要消灭的形态。
{
  assert.equal(resolveOnnxSlots({ observation_kind: 'go2_rl_sdk_45' }, ROBUST_IN, ROBUST_OUT), null);
  assert.equal(resolveOnnxSlots(null, ROBUST_IN, ROBUST_OUT), null);
  assert.throws(() => resolveOnnxSlots({ onnx_slots: {} }, ROBUST_IN, ROBUST_OUT), '空槽表 = 半声明，必须抛');
  assert.throws(
    () => resolveOnnxSlots({ onnx_slots: { outputs: { action: 10 } } }, ROBUST_IN, ROBUST_OUT),
    '只有 outputs、没有 inputs 也是半声明',
  );
  console.log('OK 未声明槽表返回 null；半声明（空/只有 outputs）抛错');
}

// 4) fail-closed：声明与网络不符、槽名不认识、输出索引越界 —— 一律抛，不许就近落一个
{
  const bad = [
    [{ onnx_slots: { inputs: ['actor', 'is_init'] } }, '少声明两路'],
    [{ onnx_slots: { inputs: ['actor', 'is_init', 'adapt_hx', 'command_', 'extra'] } }, '多声明一路'],
    [{ onnx_slots: { inputs: ['actor', 'is_init', 'adapt_hx', 'cmd_typo'] } }, '槽名拼错'],
    // 注意：`['is_init','actor',…]` **不是**"缺 actor"（actor 只是位置不同）——位置无关，
    // 缺 actor 得靠"四路全用别的槽名"构造（重复槽名是另一种真错法，一并钉住）
    [{ onnx_slots: { inputs: ['is_init', 'is_init', 'adapt_hx', 'command_'] } }, '缺 actor（重复槽名）'],
    [{ onnx_slots: { inputs: ['actor', 'is_init', 'adapt_hx', 'command_'], outputs: { action: 99 } } }, '输出索引越界'],
    [{ onnx_slots: { inputs: ['actor', 'is_init', 'adapt_hx', 'command_'], outputs: { action: -1 } } }, '负索引'],
  ];
  for (const [contract, why] of bad) {
    assert.throws(() => resolveOnnxSlots(contract, ROBUST_IN, ROBUST_OUT), why);
  }
  console.log('OK fail-closed：路数不符 / 槽名未知 / 输出越界 全部抛错');
}

// 5) 白名单自检：`is_init` 这类运行时槽名不许被悄悄扩写（扩写要先改这里与本文件头注释）
{
  assert.deepEqual(SLOT_KINDS, ['actor', 'is_init', 'adapt_hx', 'command_']);
  console.log('OK 槽名白名单与文档一致');
}

console.log('\nFINAL onnx_slots.test.mjs: 5 组断言全部通过 ✔');
