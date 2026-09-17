// ONNX metadata_props ↔ 契约校验单测（自包含断言，与 raycast / sensor_dock 同风格，
// `node web/sim2sim/onnx_contract_check.test.mjs` 直接跑）。
//
// 钉的是 G3「加载即校验」的规则，不只是扫描器输出：
//   · protobuf 扫描器对**真实包内 onnx**（有章 / 无章各一）的输出；
//   · 相符放行（含用真实包契约 + 真实带章策略做的回归：存量 11 条带章策略一条都不能被误杀）；
//   · 不符硬拒，且违规原因能落到**具体字段 + 期望 vs 实际**；
//   · 「没有元数据可校验」的两态（missing 放行 + 如实提示）与「有章不符」（reject）严格区分；
//   · 实测过的脏值也要兜住：g1/go2w 的 clip_actions 是**空串**、m20 的增益是 "80.0000,…"。
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  checkOnnxMetadataContract,
  contractSummaryFromConfig,
  formatContractViolations,
  scanOnnxMetadata,
} from "./onnx_contract_check.js";

const STAMPED_URL = new URL(
  "../../assets/robots/deeprobotics_m20/simulation/policies/m20_velocity_57.onnx",
  import.meta.url,
);
const UNSTAMPED_URL = new URL(
  "../../assets/robots/deeprobotics_m20/simulation/policies/m20_official_sdk.onnx",
  import.meta.url,
);
const GO2W_LEGS_URL = new URL(
  "../../assets/robots/unitree_go2w/simulation/policies/unitree_velocity_legs.onnx",
  import.meta.url,
);
const GO2W_CONFIG_URL = new URL(
  "../../assets/robots/unitree_go2w/simulation/config.json",
  import.meta.url,
);
const M20_CONTRACT_URL = new URL(
  "../../assets/robots/deeprobotics_m20/contract_v3.json",
  import.meta.url,
);

const stampedScan = scanOnnxMetadata(new Uint8Array(readFileSync(STAMPED_URL)));
const unstampedScan = scanOnnxMetadata(new Uint8Array(readFileSync(UNSTAMPED_URL)));
const go2wLegsScan = scanOnnxMetadata(new Uint8Array(readFileSync(GO2W_LEGS_URL)));
const m20Order = JSON.parse(readFileSync(M20_CONTRACT_URL, "utf8")).action.joint_order;

// 1) 扫描器 × 真实带章 onnx（m20_velocity_57：mjlab 导出 + build_deploy_metadata 盖章）
{
  assert.equal(stampedScan.ok, true, "真实带章 onnx 必须能扫出来");
  const meta = stampedScan.metadata;
  assert.equal(meta.joint_names.split(",").length, 16, "m20 是 16 关节");
  assert.equal(meta.joint_stiffness.split(",").length, 16, "joint_stiffness 逐关节盖章");
  assert.ok(meta.action_scale.split(",").every((v) => Number.isFinite(Number(v))), "action_scale 全数值");
  // 实测：m20 是旧版导出器盖的章，只有 checkpoint_path/base_link_name 等信息键、
  // 没有 observation_names（新版 native_worker.build_deploy_metadata 才有）——
  // 校验器对"部分盖章"必须照常工作，所以这里钉住这个真实形状。
  assert.ok(meta.checkpoint_path, "信息键 checkpoint_path 存在但不参与判定");
}

// 2) 扫描器 × 真实无章 onnx（m20_official_sdk：官方 SDK 导入，无 metadata_props）
{
  assert.equal(unstampedScan.ok, true, "无章 onnx 扫描不能报错");
  assert.deepEqual(unstampedScan.metadata, {}, "无 metadata_props ⇒ 空字典");
}

// 3) 扫描器 × 损坏字节：返回 {ok:false} 而不是抛异常（调用方按 missing 放行，交给 ort 把关）
{
  const garbage = scanOnnxMetadata(new Uint8Array([0x08, 0x96, 0x01, 0x2a, 0xff]));
  assert.equal(garbage.ok, false, "截断/非法 wire type ⇒ ok:false");
  assert.ok(garbage.error.includes("ONNX protobuf"), `错误要可读：${garbage.error}`);
}

// 4) contractSummaryFromConfig：普通 16 关节 + go2w 腿子集（action_joint_order 覆盖）
{
  const plain = contractSummaryFromConfig({
    robot: { joint_order: m20Order },
    policy: { contract: { obs_dim: 71, action_dim: 16, action_scale: 0.25 } },
  });
  assert.deepEqual(plain.slots, m20Order, "无 action_joint_order ⇒ 用模型 joint_order 前 action_dim 个");
  assert.equal(plain.actionDim, 16);
  assert.equal(plain.clipActions, null, "契约没声明 clip ⇒ 不比 clip");

  const legs = contractSummaryFromConfig({
    robot: { joint_order: ["a", "b", "c", "wheel_fl", "wheel_fr", "x", "y"] },
    policy: { contract: { action_dim: 3, action_joint_order: ["a", "c", "b"] } },
  });
  assert.deepEqual(legs.slots, ["a", "c", "b"], "腿子集策略：动作槽序来自 contract.action_joint_order");

  const clip = contractSummaryFromConfig({
    robot: { joint_order: m20Order },
    policy: { contract: { action_dim: 16, clip_actions: "10" } },
  });
  assert.equal(clip.clipActions, 10, "契约 clip_actions（字符串数字）转数值");
}

// 5) 相符放行：真实带章策略 × **真实包契约**推导的期望序（存量带章策略回归）
{
  const check = checkOnnxMetadataContract(stampedScan.metadata, {
    slots: m20Order,
    actionDim: 16,
    clipActions: null,
  });
  assert.equal(check.status, "ok", `m20 带章策略对包契约必须放行：${formatContractViolations(check)}`);
  assert.deepEqual(check.violations, []);
  assert.equal(check.info.jointCount, 16);
}

// 6) 相符放行（go2w 腿子集）：用包内 simulation/config.json 的 policy contract 推导
{
  const config = JSON.parse(readFileSync(GO2W_CONFIG_URL, "utf8"));
  const entry = config.policies.find((p) => p.id === "go2w-velocity-legs");
  assert.ok(entry, "包内必须声明 go2w-velocity-legs");
  const summary = contractSummaryFromConfig({
    robot: { joint_order: Array.from({ length: 16 }, (_, i) => `j${i}`) },
    policy: { contract: entry.contract },
  });
  assert.equal(summary.slots.length, 12, "腿子集只校验 12 个腿槽位");
  const check = checkOnnxMetadataContract(go2wLegsScan.metadata, summary);
  assert.equal(check.status, "ok", `go2w 腿子集带章策略必须放行：${formatContractViolations(check)}`);
}

// 7) 不符硬拒：关节数不一致 → reject，原因落到字段 + 期望 vs 实际
{
  const meta = { joint_names: stampedScan.metadata.joint_names.split(",").slice(0, 12).join(",") };
  const check = checkOnnxMetadataContract(meta, { slots: m20Order, actionDim: 16, clipActions: null });
  assert.equal(check.status, "reject");
  const v = check.violations[0];
  assert.equal(v.field, "joint_names");
  assert.ok(v.reason.includes("关节数"), `原因要说清是什么不符：${v.reason}`);
  assert.ok(v.expected.includes("16") && v.actual.includes("12"), `期望 vs 实际要可读：${v.expected} / ${v.actual}`);
  assert.ok(
    formatContractViolations(check).includes("joint_names"),
    "格式化文案必须点名违规字段",
  );
}

// 8) 不符硬拒：槽数相同但**顺序**错 → reject，指认到槽位
{
  const swapped = m20Order.slice();
  [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
  const check = checkOnnxMetadataContract(
    { joint_names: swapped.join(",") },
    { slots: m20Order, actionDim: 16, clipActions: null },
  );
  assert.equal(check.status, "reject", "顺序错了不能因为数量对就放行");
  assert.ok(check.violations[0].reason.includes("顺序"), `原因要指认顺序：${check.violations[0].reason}`);
  assert.ok(check.violations[0].actual.includes("槽 0"), `要落到具体槽位：${check.violations[0].actual}`);
}

// 9) 不符硬拒：动作槽对齐键长度错（action_scale 既不是关节数也不是合法标量）
{
  const base = { joint_names: stampedScan.metadata.joint_names };
  const badScale = { ...base, action_scale: "0.25,0.25" };
  const check = checkOnnxMetadataContract(badScale, { slots: m20Order, actionDim: 16, clipActions: null });
  assert.equal(check.status, "reject");
  assert.equal(check.violations[0].field, "action_scale");
  assert.ok(check.violations[0].reason.includes("joint_names=16"), `要对齐到盖章关节数：${check.violations[0].reason}`);

  // 没有 joint_names 时退回对契约 action_dim 比
  const check2 = checkOnnxMetadataContract(badScale, { slots: m20Order, actionDim: 16, clipActions: null });
  assert.equal(check2.violations[0].field, "action_scale");

  // 标量 action_scale 合法（实测 microduck 7 条 + go2-pie 盖的是单值）
  const scalar = checkOnnxMetadataContract(
    { ...base, action_scale: "0.25" },
    { slots: m20Order, actionDim: 16, clipActions: null },
  );
  assert.equal(scalar.status, "ok", `标量 action_scale 不能拒：${formatContractViolations(scalar)}`);

  // 实测腿子集形状（go2w-velocity-legs）：12 个名字 + 全模型长度的增益/默认角数组
  //（16 项、轮子填 0）是后端正常盖章 ⇒ 增益类数组不做长度硬校验
  const go2wShape = checkOnnxMetadataContract(
    {
      joint_names: Array.from({ length: 12 }, (_, i) => `leg${i}`).join(","),
      joint_stiffness: Array.from({ length: 16 }, () => "20").join(","),
      default_joint_pos: Array.from({ length: 16 }, () => "0").join(","),
      action_scale: Array.from({ length: 12 }, () => "0.35").join(","),
    },
    { slots: Array.from({ length: 12 }, (_, i) => `leg${i}`), actionDim: 12, clipActions: null },
  );
  assert.equal(go2wShape.status, "ok", `后端腿子集盖章形状必须放行：${formatContractViolations(go2wShape)}`);
}

// 10) 不符硬拒：数值数组里混进非数值（元数据被改写/损坏）
{
  const check = checkOnnxMetadataContract(
    { joint_names: stampedScan.metadata.joint_names, joint_damping: "1.5,abc,0.5" },
    { slots: m20Order, actionDim: 16, clipActions: null },
  );
  assert.equal(check.status, "reject");
  assert.equal(check.violations[0].field, "joint_damping");
  assert.ok(check.violations[0].reason.includes("非数值"), `要说明是数值损坏：${check.violations[0].reason}`);
}

// 11) 不符硬拒：clip_actions 双方都声明且数值不一致
{
  const check = checkOnnxMetadataContract(
    { joint_names: stampedScan.metadata.joint_names, clip_actions: "100" },
    { slots: m20Order, actionDim: 16, clipActions: 10 },
  );
  assert.equal(check.status, "reject");
  assert.equal(check.violations[0].field, "clip_actions");
}

// 12) clip_actions 的实测脏值兜底：g1/go2w 导出写的是**空串**；逐关节 clip 不与标量硬比
{
  const empty = checkOnnxMetadataContract(
    { joint_names: stampedScan.metadata.joint_names, clip_actions: "  " },
    { slots: m20Order, actionDim: 16, clipActions: 10 },
  );
  assert.equal(empty.status, "ok", `空串 clip_actions 不能误杀（g1/go2w 实测如此）：${formatContractViolations(empty)}`);

  const perJoint = checkOnnxMetadataContract(
    { joint_names: stampedScan.metadata.joint_names, clip_actions: "100,80,100,80" },
    { slots: m20Order, actionDim: 16, clipActions: 10 },
  );
  assert.equal(perJoint.status, "ok", "逐关节 clip 与契约标量语义不同 ⇒ 提示不硬拒");
  assert.ok(perJoint.warnings.some((w) => w.includes("clip_actions")), "但要如实提示没比");
}

// 13) 诚实边界·两态：没章 → missing（放行），只有信息键 → missing；有章不符 → reject
{
  for (const meta of [null, undefined, {}, { run_path: "runs/foo" }, { source: "unitree" }]) {
    const check = checkOnnxMetadataContract(meta, { slots: m20Order, actionDim: 16, clipActions: null });
    assert.equal(check.status, "missing", `无章/仅信息键 ⇒ missing：${JSON.stringify(meta)}`);
    assert.deepEqual(check.violations, [], "missing 不是违规");
    assert.ok(check.warnings.length >= 1, "missing 必须带如实提示文案");
    assert.ok(
      check.warnings[0].includes("没有元数据盖章") || check.warnings[0].includes("没有可校验"),
      `提示要说明为什么跳过：${check.warnings[0]}`,
    );
  }

  const stampedMeta = { joint_names: m20Order.join(",") };
  const mismatch = checkOnnxMetadataContract(
    { joint_names: stampedMeta.joint_names.slice(0, -1) },
    { slots: m20Order, actionDim: 16, clipActions: null },
  );
  assert.equal(mismatch.status, "reject", "有章不符必须硬拒，不能混进 missing");
}

// 14) 槽长为空/未知时的降级：无法比对要给 warning，不许假装校验通过
{
  const check = checkOnnxMetadataContract(
    { joint_names: stampedScan.metadata.joint_names },
    { slots: [], actionDim: 0, clipActions: null },
  );
  assert.equal(check.status, "ok", "契约缺失不是策略的错，不硬拒");
  assert.ok(check.warnings.some((w) => w.includes("joint_names 无法比对")), "但必须承认没比成");
}

console.log("onnx_contract_check: 14 checks ok");
