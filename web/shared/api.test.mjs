// 前端 API 调用单测（自包含断言，与 sim2sim 各 *.test.mjs 同风格：
// `node web/shared/api.test.mjs` 直接跑）。
//
// 钉的是"裸 fetch 会静默吞掉的东西"：
//   · 4xx/5xx **必须抛**（错误体绝不当数据）—— dashboard.js 那 6 处的实际缺陷；
//   · 抛出的错误要能拿到 status 与后端 detail（否则页面只能显示"加载失败"）；
//   · 超时与网络不可达分开说；
//   · 非 JSON 响应明确报错，而空响应体（204）返回 null；
//   · ApiError 的跨世界可用性（普通脚本用全局、module 用 import）。
import assert from "node:assert/strict";
import api from "./api.js";

const { ApiError, fetchJson, fetchJsonBody, messageOf, detailOf } = api;

const originalFetch = globalThis.fetch;
const originalAbort = globalThis.AbortController;

/** 造一个假 fetch：记录调用参数，按脚本返回响应。 */
function stubFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return handler(url, init);
  };
  return calls;
}

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(payload),
  };
}

async function expectApiError(promise, message) {
  try {
    await promise;
  } catch (error) {
    assert.ok(error instanceof ApiError, message + "（应抛 ApiError，实得 " + error + "）");
    return error;
  }
  throw new Error(message + "（没有抛出）");
}

// 1) 正常 JSON 响应原样返回
{
  stubFetch(() => jsonResponse({ tasks: [], count: 0 }));
  const data = await fetchJson("/api/training/list");
  assert.deepEqual(data, { tasks: [], count: 0 });
}

// 2) 4xx/5xx 必须抛，且带 status 与后端 detail（dashboard.js 的缺陷就在这条）
{
  stubFetch(() => jsonResponse({ detail: "训练服务未就绪" }, 500));
  const error = await expectApiError(fetchJson("/api/training/list"), "500 应抛错而不是当数据");
  assert.equal(error.status, 500);
  assert.equal(error.detail, "训练服务未就绪");
  assert.match(error.message, /训练服务未就绪/, "错误消息要带后端原话");
}

// 3) detail 是对象形态（FastAPI 的 422 常见）也要取到人能读的那句
{
  stubFetch(() => jsonResponse({ detail: { message: "字段 robot_id 缺失" } }, 422));
  const error = await expectApiError(fetchJson("/api/x"), "422 应抛错");
  assert.equal(error.status, 422);
  assert.equal(error.detail, "字段 robot_id 缺失");
  assert.equal(detailOf({ detail: { message: "字段 robot_id 缺失" } }), "字段 robot_id 缺失");
}

// 4) 4xx 但没有可读 detail 时，消息里保留 URL（不让调用方拿到空消息）
{
  stubFetch(() => jsonResponse({}, 404));
  const error = await expectApiError(fetchJson("/api/missing"), "404 应抛错");
  assert.equal(error.status, 404);
  assert.match(error.message, /\/api\/missing/);
}

// 5) 非 JSON 响应（例如静态页/网关 HTML）明确报错，而不是返回 null
{
  stubFetch(() => ({ ok: true, status: 200, text: async () => "<html>502 Bad Gateway</html>" }));
  const error = await expectApiError(fetchJson("/api/x"), "非 JSON 响应应抛错");
  assert.match(error.message, /不是 JSON/);
}

// 6) 空响应体（204）返回 null——合法的"成功但无内容"
{
  stubFetch(() => ({ ok: true, status: 204, text: async () => "" }));
  assert.equal(await fetchJson("/api/x"), null);
}

// 7) 网络不可达与超时分开说
{
  stubFetch(() => { throw new TypeError("Failed to fetch"); });
  const error = await expectApiError(fetchJson("/api/x"), "网络错误应抛 ApiError");
  assert.match(error.message, /网络不可达/);

  globalThis.AbortController = class {
    constructor() { this.signal = {}; }
    abort() { this.aborted = true; }
  };
  stubFetch(() => {
    const abortError = new Error("aborted");
    abortError.name = "AbortError";
    throw abortError;
  });
  const timeoutError = await expectApiError(
    fetchJson("/api/slow", { timeoutMs: 5 }), "超时也应抛 ApiError",
  );
  assert.match(timeoutError.message, /请求超时/);
  globalThis.AbortController = originalAbort;
}

// 8) POST 封装：body 序列化 + Content-Type 一处写好
{
  const calls = stubFetch(() => jsonResponse({ ok: true }));
  await fetchJsonBody("/api/training/create", { robot_id: "go2" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].init.body), { robot_id: "go2" });
}

// 9) 超时定时器要清掉（否则每次调用都留一个悬挂的 timer）
{
  const calls = stubFetch(() => jsonResponse({ ok: true }));
  const before = process._getActiveHandles ? process._getActiveHandles().length : 0;
  await fetchJson("/api/x", { timeoutMs: 60000 });
  const after = process._getActiveHandles ? process._getActiveHandles().length : 0;
  assert.ok(after <= before, "请求结束后不应残留 timer（before=" + before + " after=" + after + "）");
  assert.equal(calls.length, 1);
}

// 10) messageOf：ApiError 给后端原话，其它异常给自身消息
{
  assert.equal(messageOf(new ApiError("接口 500：出错了")), "接口 500：出错了");
  assert.equal(messageOf(new Error("boom")), "boom");
}

// 11) 源码面（防回归）：除本文件外，`web/` 里不许再有"自建 JSON fetch 封装"。
//
// 判据是"函数体里直接 `await fetch(`"——委托型（`return LSApi.fetchJson(...)`）不含它，
// 所以薄封装可以有很多个，实现只能有一个。这条扫的是 2026-09-19 的三份历史实现
// （training-common.js / workbench.js / dashboard 的散点）。
{
  const { readdirSync, readFileSync, statSync } = await import("node:fs");
  const { join } = await import("node:path");
  // Windows 上 `new URL(...).pathname` 是 "/C:/..."，拼出来的路径会被当成
  // 相对盘符（C:\C:\...）直接 ENOENT —— 用 fileURLToPath 取本机路径。
  const { fileURLToPath } = await import("node:url");
  const root = fileURLToPath(new URL(".", import.meta.url)).replace(/[\\/]$/, "");
  const webRoot = join(root, "..");

  function walk(dir, out = []) {
    for (const entry of readdirSync(dir)) {
      if (entry === "vendor" || entry === "node_modules") continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, out);
      else if (entry.endsWith(".js") && !entry.endsWith(".test.mjs")) out.push(full);
    }
    return out;
  }

  const offenders = [];
  for (const file of walk(webRoot)) {
    if (file === join(root, "api.js")) continue;
    const text = readFileSync(file, "utf8");
    const re = /(?:async\s+)?function\s+([A-Za-z_$][\w$]*[Ff]etch[\w$]*)\s*\(/g;
    let match;
    while ((match = re.exec(text))) {
      const body = text.slice(match.index, match.index + 900);
      if (body.includes("await fetch(")) offenders.push(file.replace(webRoot, "web") + "::" + match[1]);
    }
  }
  assert.deepEqual(offenders, [], "JSON fetch 封装应只在 web/shared/api.js：" + offenders.join(", "));
}

globalThis.fetch = originalFetch;
console.log("api.test.mjs: 11 组断言全部通过 ✔");
