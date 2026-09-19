// ONNX metadata_props ↔ browser-config 契约校验（G3「加载即校验」收口）。
//
// 纯函数模块：不读 sim / DOM / fetch，输入要么是 scanOnnxMetadata 扫出来的
// metadata 字典，要么是 browser-config（/api/simulation/browser-config）的
// policy/robot 段——Node 单测可以直接喂真实文件与真实 config。
//
// ---------------------------------------------------------------------------
// 调研证据（2026-09-17 实测，键名不臆造）：
//
// 1) 后端盖章了什么 —— adapters/mjlab/onnx_exporter.attach_metadata_to_onnx
//    （list/tuple 用 "," 连接，标量 str()）+ adapters/mjlab/native_worker.py
//    build_deploy_metadata / stamp_contract_extras。真实写入键：
//      joint_names / joint_stiffness / joint_damping / default_joint_pos /
//      observation_names / command_names / action_scale / clip_actions（可选）/
//      joint_ids_map（可选）/ observation_history_lengths（JSON 串，可选）
//    另有上游自带的信息键（只展示、不校验）：run_path / source /
//    checkpoint_path / action_names / base_link_name。
//
// 2) 浏览器手里有什么契约 —— backend/simulation_api.browser_simulation_config
//    下发 robot.joint_order（模型序）、policy.contract.{obs_dim, action_dim,
//    history_len, action_joint_order?, action_scale?, clip_actions?…}。
//    「期望动作槽序」按 app.js applyRuntimeConfig 同一套规则推导：
//    contract.action_joint_order（腿子集策略）优先，否则 robot.joint_order，
//    截到 action_dim。
//
// 3) 仓库实测覆盖率（用本模块的扫描器逐文件扫 assets/robots + web/sim2sim/models）：
//    48 个打包 onnx 里 11 个带 metadata_props，且 11/11 都带 joint_names；
//    45 条包内声明的策略（backend.policy_artifacts 解析）中 11 条带章，并用
//    包内 contract_truth + 各自 policy contract 比对全部一致（含 go2w 腿子集
//    12 槽、g1 29 关节）。34/45 条历史/第三方导入策略完全没有元数据
//    （himloco/robotlab/rlsar/kaiwu/zex-w…），硬拒它们等于废掉 3/4 策略库。
//
// 诚实边界（有意区分的两种「不拒」）：
//   · 「没有元数据可校验」（无章 / 无 joint_names / 扫描失败）→ status="missing"，
//     放行但状态栏如实提示（历史导入策略覆盖 3/4，只能跳过，不能硬拒）；
//   · 「有元数据但不符」→ status="reject"，加载路径必须在创建推理会话前抛错，
//     中文说明哪个字段、期望 vs 实际，绝不静默降级成警告后照跑。
//   只校验「确实盖章且可靠可比」的字段：关节序（硬校验）、数值数组可解析性
//   （硬校验）、action_scale/joint_ids_map 长度（硬校验，动作槽对齐）、
//   clip_actions 数值（双方都声明才比）。joint_stiffness/joint_damping/
//   default_joint_pos 不比长度——实测腿子集/轮足策略（go2w-velocity-legs）
//   后端盖的就是「全模型长度」（12 名字 + 16 数值），浏览器侧没有可靠的全模型
//   长度可比；增益数值也不比——浏览器侧增益允许 per-policy 覆盖
//   （applyRuntimeConfig 的 rl_kp/rl_kd 逻辑），按值比对会误杀合法策略。
// ---------------------------------------------------------------------------

/** 逐关节、以逗号分隔的数值数组键（导出器 ",".join 写法；只做可解析性硬校验）。
 * 长度不硬校验——实测（11 条带章策略逐一核对）后端对**腿子集/轮足**策略会盖
 * 「全模型长度」的增益数组：go2w-velocity-legs 是 joint_names=12 而
 * joint_stiffness/joint_damping/default_joint_pos=16（4 个轮执行器填 0），
 * 浏览器侧拿不到可靠的全模型长度可比。action_scale / joint_ids_map 例外，
 * 它们语义上对齐动作槽，见下。 */
const PER_JOINT_NUMERIC_KEYS = [
  "joint_stiffness",
  "joint_damping",
  "default_joint_pos",
];

/** 语义上与「动作槽数」对齐的数值数组：长度必须 = 关节数，**或 = 1**（标量
 * action_scale 合法——实测 microduck 7 条与 go2-pie 都盖的是单值）。 */
const ACTION_SLOT_NUMERIC_KEYS = [
  "action_scale",
  "joint_ids_map",
];

/**
 * 极简 ONNX protobuf 顶层扫描：只提取 metadata_props（ModelProto field 14）。
 * 从 app.js 原样迁来：vendored onnxruntime-web 是精简版、没有
 * InferenceSession.metadata API，所以自己读模型字节。
 * StringStringEntryProto: key = field 1, value = field 2（都是 length-delim 字符串）。
 * ModelProto 顶层没有 group 字段，wire type 3/4 视为损坏字节。
 * @param {Uint8Array} bytes 完整 ONNX 字节
 * @returns {{ok: true, metadata: Record<string, string>} | {ok: false, error: string}}
 */
export function scanOnnxMetadata(bytes) {
  try {
    return { ok: true, metadata: readOnnxMetadataBytes(bytes) };
  } catch (error) {
    // 截断/非法字节可能以 DataView RangeError 形式抛出——统一带上可读前缀，
    // 调用方（app.js 按 missing 放行的路径）要能把原因写进状态栏。
    const msg = String(error?.message || error);
    return {
      ok: false,
      error: msg.includes("ONNX protobuf") ? msg : `ONNX protobuf: 无法读取元数据（${msg}）`,
    };
  }
}

function readOnnxMetadataBytes(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder();
  const cursor = { pos: 0 };
  const readVarint = () => {
    let result = 0, shift = 0;
    for (;;) {
      const b = view.getUint8(cursor.pos);
      cursor.pos += 1;
      result += (b & 0x7f) * Math.pow(2, shift);
      if (!(b & 0x80)) return result;
      shift += 7;
    }
  };
  const readSlice = () => {
    const len = readVarint();
    const slice = bytes.subarray(cursor.pos, cursor.pos + len);
    cursor.pos += len;
    return slice;
  };
  const readString = (slice) => decoder.decode(slice);
  const meta = {};
  while (cursor.pos < bytes.length) {
    const tag = readVarint();
    const field = tag >>> 3;
    const wire = tag & 7;
    if (wire === 0) {
      readVarint();
    } else if (wire === 1) {
      cursor.pos += 8;
    } else if (wire === 5) {
      cursor.pos += 4;
    } else if (wire === 2) {
      const slice = readSlice();
      if (field !== 14) continue;
      const inner = { pos: 0 };
      const innerVarint = () => {
        let result = 0, shift = 0;
        for (;;) {
          const b = slice[inner.pos];
          inner.pos += 1;
          result += (b & 0x7f) * Math.pow(2, shift);
          if (!(b & 0x80)) return result;
          shift += 7;
        }
      };
      let key = null;
      let value = null;
      while (inner.pos < slice.length) {
        const tag2 = innerVarint();
        if ((tag2 & 7) !== 2) { inner.pos = slice.length; break; }
        const len2 = innerVarint();
        const s = readString(slice.subarray(inner.pos, inner.pos + len2));
        inner.pos += len2;
        if ((tag2 >>> 3) === 1) key = s;
        else if ((tag2 >>> 3) === 2) value = s;
      }
      if (key !== null) meta[key] = value ?? "";
    } else {
      throw new Error(`ONNX protobuf: 未知 wire type ${wire} @${cursor.pos}`);
    }
  }
  return meta;
}

/**
 * 从 browser-config payload 推导「期望动作槽序」等契约摘要。
 * 规则与 app.js applyRuntimeConfig 对 action 槽的推导一致（腿子集策略用
 * contract.action_joint_order 覆盖模型前 N 关节序）。
 * @param {object} config /api/simulation/browser-config 返回（或 switchPolicy 拼的 nextConfig）
 * @returns {{slots: string[], actionDim: number, clipActions: number|null}}
 */
export function contractSummaryFromConfig(config) {
  const contract = config?.policy?.contract || {};
  const robotOrder = Array.isArray(config?.robot?.joint_order)
    ? config.robot.joint_order.map((s) => String(s))
    : [];
  const actionJointOrder = Array.isArray(contract.action_joint_order)
    ? contract.action_joint_order.map((s) => String(s))
    : [];
  // applyRuntimeConfig: requestedActionDim = action_dim || robotOrder.length || 当前值
  const actionDim = Number(contract.action_dim || robotOrder.length || 0);
  let order = robotOrder;
  if (
    actionJointOrder.length > 0
    && actionDim > 0
    && actionJointOrder.length >= actionDim
  ) {
    order = actionJointOrder;
  }
  const slots = actionDim > 0 ? order.slice(0, actionDim) : order;
  const clipRaw = Number(contract.clip_actions);
  return {
    slots,
    actionDim,
    clipActions: Number.isFinite(clipRaw) && clipRaw > 0 ? clipRaw : null,
  };
}

function splitNames(csv) {
  return String(csv).split(",").map((s) => s.trim()).filter((s) => s.length > 0);
}

function parseNumericList(csv) {
  const raw = String(csv).split(",");
  const values = [];
  for (const piece of raw) {
    const n = Number(piece.trim());
    if (!Number.isFinite(n)) return null;
    values.push(n);
  }
  return values;
}

/**
 * 契约校验主入口（纯函数）。
 * @param {Record<string, string>|null|undefined} metadata scanOnnxMetadata 的产物（可为空）
 * @param {{slots: string[], actionDim: number, clipActions: number|null}} summary contractSummaryFromConfig 的产物
 * @returns {{status: "ok"|"reject"|"missing", violations: Array, warnings: string[], info: object}}
 *   violations 条目形如 { field, reason, expected, actual }（全部中文，供直接展示）。
 */
export function checkOnnxMetadataContract(metadata, summary) {
  const violations = [];
  const warnings = [];
  const meta = metadata && typeof metadata === "object" ? metadata : {};
  const slots = Array.isArray(summary?.slots) ? summary.slots.map((s) => String(s)) : [];
  const actionDim = Number(summary?.actionDim) || 0;

  const jointNamesCsv = typeof meta.joint_names === "string" ? meta.joint_names.trim() : "";
  const stampedJoints = jointNamesCsv ? splitNames(jointNamesCsv) : null;

  // ---- 硬校验 ①：关节序（唯一同时盖章了「数量 + 顺序」的键）----
  if (stampedJoints) {
    if (slots.length === 0) {
      // 后端总会下发 joint_order/action_dim；走到这说明契约段异常，如实提示但不算「不符」。
      warnings.push("契约未提供动作关节序，joint_names 无法比对");
    } else if (stampedJoints.length !== slots.length) {
      violations.push({
        field: "joint_names",
        reason: "关节数与契约不符",
        expected: `${slots.length} 个动作槽（${slots.join(", ")}）`,
        actual: `${stampedJoints.length} 个关节（${stampedJoints.join(", ")}）`,
      });
    } else {
      const bad = [];
      for (let i = 0; i < slots.length; i += 1) {
        if (stampedJoints[i] !== slots[i]) bad.push(`槽 ${i}: 元数据=${stampedJoints[i]} 契约=${slots[i]}`);
      }
      if (bad.length) {
        violations.push({
          field: "joint_names",
          reason: "关节顺序与契约不一致",
          expected: slots.join(", "),
          actual: `${stampedJoints.join(", ")}（${bad.slice(0, 3).join("; ")}${bad.length > 3 ? "…" : ""}）`,
        });
      }
    }
  }

  // ---- 硬校验 ②：数值数组可解析性（损坏/被改写即拒）。
  // 长度只对「动作槽对齐键」（action_scale / joint_ids_map）硬比：长度必须等于
  // 盖章关节数，或为 1（标量 action_scale 合法——实测 microduck 7 条与 go2-pie
  // 都盖单值）。joint_stiffness/joint_damping/default_joint_pos 不比长度（见上表）。
  const referenceLen = stampedJoints
    ? stampedJoints.length
    : (actionDim > 0 ? actionDim : 0);
  const checkNumericArray = (key, checkLength) => {
    const raw = typeof meta[key] === "string" ? meta[key].trim() : "";
    if (!raw) return; // 没盖章就不比（导出器对可选键本来就缺省）
    const values = parseNumericList(raw);
    if (!values) {
      violations.push({
        field: key,
        reason: "存在非数值项（元数据损坏或被改写）",
        expected: "逗号分隔的数字",
        actual: raw.length > 40 ? `${raw.slice(0, 40)}…` : raw,
      });
      return;
    }
    if (!checkLength || referenceLen <= 0) return;
    if (values.length !== referenceLen && values.length !== 1) {
      violations.push({
        field: key,
        reason: stampedJoints
          ? `长度与盖章关节数不符（joint_names=${referenceLen}）`
          : `长度与契约 action_dim 不符（${referenceLen}）`,
        expected: `${referenceLen} 个数值（或 1 个标量）`,
        actual: `${values.length} 个数值`,
      });
    }
  };
  for (const key of PER_JOINT_NUMERIC_KEYS) checkNumericArray(key, false);
  for (const key of ACTION_SLOT_NUMERIC_KEYS) checkNumericArray(key, true);

  // ---- 硬校验 ③：clip_actions（双方都声明了数值才比；实测 g1/go2w 该键可能是空串）----
  const clipRaw = typeof meta.clip_actions === "string" ? meta.clip_actions.trim() : "";
  if (clipRaw) {
    const stamped = parseNumericList(clipRaw);
    if (!stamped || stamped.length === 0) {
      violations.push({
        field: "clip_actions",
        reason: "不是可解析的动作裁剪界",
        expected: "正数（或逗号分隔的逐关节数值）",
        actual: clipRaw.length > 40 ? `${clipRaw.slice(0, 40)}…` : clipRaw,
      });
    } else if (summary?.clipActions != null) {
      const mean = stamped.reduce((a, b) => a + b, 0) / stamped.length;
      const uniform = stamped.every((v) => Math.abs(v - stamped[0]) < 1e-9);
      if (!uniform) {
        // 逐关节 clip 与契约标量本来就不是同一语义，浏览器侧按 applyActionClip 各自处理，不硬比
        warnings.push(`clip_actions 为逐关节数值（${stamped.length} 项），契约只声明标量 ${summary.clipActions}，不做数值比对`);
      } else if (Math.abs(mean - summary.clipActions) > 1e-6 * Math.max(1, Math.abs(summary.clipActions))) {
        violations.push({
          field: "clip_actions",
          reason: "动作裁剪界与契约不符",
          expected: String(summary.clipActions),
          actual: String(mean),
        });
      }
    }
  }

  // ---- 诚实边界：没有任何可校验的盖章 → missing（放行但如实提示）----
  const hasCheckableStamp = Boolean(stampedJoints)
    || PER_JOINT_NUMERIC_KEYS.some((key) => typeof meta[key] === "string" && meta[key].trim())
    || Boolean(clipRaw);
  if (Object.keys(meta).length === 0) {
    return {
      status: "missing",
      violations: [],
      warnings: ["策略 ONNX 没有元数据盖章，跳过契约校验（历史/第三方导入策略）"],
      info: { jointCount: 0, source: null, jointIdsMap: null },
    };
  }
  if (!hasCheckableStamp) {
    return {
      status: "missing",
      violations: [],
      warnings: [`策略 ONNX 元数据只有信息键（${Object.keys(meta).join(", ")}），没有可校验的部署契约盖章`],
      info: { jointCount: 0, source: meta.source || null, jointIdsMap: null },
    };
  }

  // ---- 信息键（只回传供日志展示，不参与判定）----
  let jointIdsMap = null;
  if (typeof meta.joint_ids_map === "string" && meta.joint_ids_map.trim()) {
    jointIdsMap = parseNumericList(meta.joint_ids_map);
  }
  return {
    status: violations.length ? "reject" : "ok",
    violations,
    warnings,
    info: {
      jointCount: stampedJoints ? stampedJoints.length : 0,
      source: meta.source || null,
      jointIdsMap,
    },
  };
}

/** 把 violations 压成一行中文（用于抛错文案 / 状态栏）。 */
export function formatContractViolations(result) {
  return (result?.violations || [])
    .map((v) => `[${v.field}] ${v.reason}，期望 ${v.expected}，实际 ${v.actual}`)
    .join("；");
}
