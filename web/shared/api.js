// 前端 API 调用（**唯一实现**）：HTTP 错误、超时、JSON 解析与中文错误消息只在这里写一遍。
//
// ## 为什么要它（2026-09-19 取证）
//
// 仓内 28 处 `fetch(` 分散在 6 个文件里，而 `res.ok` 的检查**并不一致**：
//
//   · `web/sim2sim/app.js` 14 处 / 17 个 `.ok` —— 基本都查；
//   · 旧 `web/dashboard.js`（2026-09-23 随双首页收敛删除）**6 处 / 0 个 `.ok`** —— 后端 4xx/5xx 的 `{"detail": ...}`
//     会被下游当成正常数据（训练列表接口 500 时页面显示"暂无训练任务"，
//     把**故障伪装成空数据**，这正是最难查的一类前端 bug）。
//
// ## 两个世界共用一个实现
//
// 本仓前端没有构建步骤，且两种加载方式并存：
//   · 普通脚本（`web/*.html` 的 `<script src>`）→ 用全局 `window.LSApi.fetchJson(...)`；
//   · ES module（`web/sim2sim/*.js`）→ `import { fetchJson } from '../shared/api.js'`
//     （node 对 CommonJS 的互操作：`module.exports` 即 default 导出）。
//
// 所以本文件写成 UMD 形态：一份实现，两个世界都能拿。
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.LSApi = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  //: 默认超时：控制面的重活（训练列表、环境探测）在冷启动时可能要十几秒。
  const DEFAULT_TIMEOUT_MS = 30000;

  /** 带 HTTP 语义的错误：调用方按 `status` 分流，按 `detail` 显示后端原话。 */
  class ApiError extends Error {
    constructor(message, { status = 0, url = '', detail = null } = {}) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.url = url;
      this.detail = detail;
    }
  }

  /** 从后端错误体里取"人能读的那句话"（FastAPI 的 detail 可能是字符串也可能是对象）。 */
  function detailOf(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const detail = payload.detail !== undefined ? payload.detail : payload.message !== undefined ? payload.message : payload.error;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail);
    return null;
  }

  /**
   * 发一次请求并把响应当 JSON 读回来。
   *
   * 与裸 `fetch` 的差别（每一条都是踩过的坑）：
   *   · **`res.ok` 必须查**：4xx/5xx 直接抛 `ApiError`（含 status 与后端 detail），
   *     绝不把错误体当数据往下传；
   *   · **超时**：默认 30s（AbortController），超时消息与网络不可达分开说；
   *   · **非 JSON 响应**：明确抛错而不是返回 `null`（否则调用方会读成"空数据"）；
   *   · 空响应体（204）返回 `null` —— 这是合法的"成功但无内容"。
   */
  async function fetchJson(url, options) {
    const settings = Object.assign({}, options);
    const timeoutMs = settings.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : settings.timeoutMs;
    delete settings.timeoutMs;

    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = controller && timeoutMs > 0 ? setTimeout(function () { controller.abort(); }, timeoutMs) : null;

    let response;
    try {
      response = await fetch(url, controller ? Object.assign({}, settings, { signal: controller.signal }) : settings);
    } catch (error) {
      const reason = error && error.name === 'AbortError'
        ? '请求超时（' + timeoutMs + 'ms）'
        : '网络不可达';
      throw new ApiError(reason + '：' + url, { url: url });
    } finally {
      if (timer) clearTimeout(timer);
    }

    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        payload = null;
      }
    }

    if (!response.ok) {
      const detail = detailOf(payload);
      throw new ApiError('接口 ' + response.status + '：' + (detail || url), {
        status: response.status,
        url: url,
        detail: detail,
      });
    }
    if (payload === null && text) {
      throw new ApiError('响应不是 JSON：' + url, { status: response.status, url: url });
    }
    return payload;
  }

  /** POST/PUT JSON 的薄封装：序列化 + Content-Type 一处写好（调用方只管 body 对象）。 */
  function fetchJsonBody(url, body, method) {
    return fetchJson(url, {
      method: method || 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body === undefined ? {} : body),
    });
  }

  /** 把任意异常翻成"能给用户看的一句话"（`ApiError` 已带后端原话，其余按网络问题说）。 */
  function messageOf(error) {
    if (error instanceof ApiError) return error.message;
    return error && error.message ? error.message : String(error);
  }

  return {
    ApiError: ApiError,
    DEFAULT_TIMEOUT_MS: DEFAULT_TIMEOUT_MS,
    detailOf: detailOf,
    fetchJson: fetchJson,
    fetchJsonBody: fetchJsonBody,
    messageOf: messageOf,
  };
});
