// ONNX **槽表**解析（`contract.onnx_slots`）—— 按**位置**把输入/输出接到语义槽上。
//
// ## 为什么必须有它（2026-09-22，mjswan 四输入链）
//
// 大多数产物的张量名是可读的（`obs` / `proprio_history` / `memory_h_in`），所以浏览器侧一直靠
// **名字约定**配对（`HISTORY_INPUT_NAMES`、`recurrentOutputName` 的 `_in → _out` 等）。但
// mjswan 导出的图长这样（实测）：
//
//   in : l_kwargs_policy_[1,117], arg1[1]bool, l_kwargs_adapt_hx_[1,128], l_kwargs_command_[1,16]
//   out: l__args___0_module_1_1   （15 个输出，`action` 在第 10、`next.adapt_hx` 在第 4）
//
// 名字是导出器按内部模块树生成的，**没有任何语义、也不能改名**；上游的约定是
// `in_keys` / `out_keys` **按位置**映射（ADR 0006 §5）。把这张表放进契约（`onnx_slots`），
// 浏览器与验收器就能用**同一份**位置映射，而不是各猜一套名字规则。
//
// ## 契约字段形状
//
// ```json
// "onnx_slots": {
//   "inputs": ["actor", "is_init", "adapt_hx", "command_"],
//   "outputs": { "action": 10, "recurrent": 4 }
// }
// ```
//
// * `inputs[i]` —— 网络**第 i 个输入**（按 `session.inputNames` 顺序）的语义槽名；
// * `outputs.action` / `outputs.recurrent` —— 网络**第 n 个输出**分别是动作与递归回传。
//
// ## 判据（fail-closed）
//
// * 声明了槽表 ⇒ **必须**与网络实际输入数一致（多一路少一路都是错绑，不猜不改）；
// * 槽名只认这一份白名单（`SLOT_KINDS`）——拼错的槽名不会"就近落一个"，直接抛；
// * 输出索引必须在该网络的输出范围内；
// * **没声明槽表**（绝大多数策略）⇒ 返回 `null`，调用方走原有的名字约定路径（行为不变）。

/** 槽位语义白名单。`actor` = 本体观测（喂 `sim.obs`），其余是运行时自己合成的量。 */
export const SLOT_KINDS = ["actor", "is_init", "adapt_hx", "command_"];

/** 递归回传槽：输入是"上一步的状态"，输出是"这一步的状态"（下一帧回灌）。 */
export const RECURRENT_SLOTS = ["adapt_hx"];

/**
 * 解析槽表并绑定到实际张量名。返回 `null` = 该策略没声明槽表（走名字约定路径）。
 *
 * @param {object} contract 策略契约（含可选 `onnx_slots`）
 * @param {string[]} inputNames  网络输入名，**顺序即位置**
 * @param {string[]} outputNames 网络输出名，**顺序即位置**
 * @returns {null | {
 *   actorName: string, commandName: string, isInitName: string, recurrentName: string,
 *   actionName: string, recurrentOutputName: string, inputSlots: string[],
 * }}
 */
export function resolveOnnxSlots(contract, inputNames, outputNames) {
  const slots = contract && contract.onnx_slots;
  if (!slots || typeof slots !== "object") return null;
  const declared = Array.isArray(slots.inputs) ? slots.inputs : null;
  if (!declared || declared.length === 0) {
    throw new Error("onnx_slots.inputs 必须是非空数组（槽名按位置对应网络的输入）");
  }
  const ins = Array.isArray(inputNames) ? inputNames : [];
  const outs = Array.isArray(outputNames) ? outputNames : [];
  if (declared.length !== ins.length) {
    throw new Error(
      `onnx_slots.inputs 声明 ${declared.length} 路（${declared.join("/")}），`
      + `而网络有 ${ins.length} 路（${ins.join("/")}）—— 按位置映射，多一路少一路都是错绑`,
    );
  }
  for (const name of declared) {
    if (!SLOT_KINDS.includes(name)) {
      throw new Error(`onnx_slots.inputs 里有未知槽名 ${JSON.stringify(name)}（只认 ${SLOT_KINDS.join(" / ")}）`);
    }
  }
  const at = (slot, fallback) => {
    const where = declared.indexOf(slot);
    return where >= 0 ? ins[where] : fallback;
  };
  const actorName = at("actor", "");
  if (!actorName) throw new Error("onnx_slots.inputs 缺少必需槽 actor（本体观测喂哪一路）");
  if (!Array.isArray(outs) && (slots.outputs && Object.keys(slots.outputs).length)) {
    throw new Error("onnx_slots.outputs 指了输出，但网络没报出输出名——无法按位置绑定");
  }
  const outputs = (slots.outputs && typeof slots.outputs === "object") ? slots.outputs : {};
  const outputAt = (value, label) => {
    if (value === undefined || value === null) return "";
    const position = Number(value);
    if (!Number.isInteger(position) || position < 0 || position >= outs.length) {
      throw new Error(`onnx_slots.outputs.${label}=${value} 越界（网络有 ${outs.length} 个输出）`);
    }
    return outs[position];
  };
  const recurrentName = RECURRENT_SLOTS.map((slot) => at(slot, "")).find(Boolean) || "";
  return {
    actorName,
    commandName: at("command_", ""),
    isInitName: at("is_init", ""),
    recurrentName,
    actionName: outputAt(outputs.action, "action"),
    recurrentOutputName: outputAt(outputs.recurrent, "recurrent"),
    inputSlots: declared.slice(),
  };
}
