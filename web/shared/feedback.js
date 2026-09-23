// 前端统一反馈（**唯一实现**）：toast 提示、确认对话框、错误出口只在这里写一遍。
//
// ## 为什么要它（2026-09-24 取证）
//
// 第 3 批审计实测：仓内散着 **3 份自建 toast**（navigation_editor.html 右下角 /
// training_create.html bottom 32px / training_monitor.html bottom 56px——三份实现只差
// 常量）与 **十余处 `alert`/`confirm`**。它们的问题不是"不好看"，而是各自为政：
//   · `alert` 会**阻塞整个页面**（轮询、图表、日志全停），且样式/措辞无从收敛；
//   · 自建 toast 各有各的 z-index / 颜色 / 超时，同一个失败在三页长得不一样；
//   · 更隐蔽的一类：失败后**什么都不显示**（静默失败），用户把"读取失败"看成"暂无数据"。
//
// 本文件与 shared/api.js 同款 UMD：普通脚本用全局 `window.LSFeedback`，
// node 侧 `require('./feedback.js')`（confirm 无 DOM 时返回 false，不抛错）。
//
// ## 视觉约定
//
// 样式全部在 shared/ui.css（`.ls-toast*` 第 1 批已有；`.ls-confirm*` 第 3 批补齐）。
// 本文件**不写任何内联样式**、不引入新色系——只做行为。
(function (root, factory) {
  const feedback = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = feedback;
  } else {
    root.LSFeedback = feedback;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  //: 单例 toast 容器（容器复用：同屏永远只有一条共享 toast，不叠罗汉）。
  const TOAST_ID = 'lsToast';
  //: 默认停留时间：错误比普通提示多留一会儿（用户需要读完后端原话）。
  const DEFAULT_TIMEOUT_MS = 2600;
  const ERROR_TIMEOUT_MS = 6000;

  //: 语义 type → ui.css 的修饰类（info 用基底类，不加修饰）。
  const TOAST_CLASSES = {
    info: '',
    ok: ' ls-toast--ok',
    success: ' ls-toast--ok',
    warn: ' ls-toast--warn',
    error: ' ls-toast--err',
    err: ' ls-toast--err',
    danger: ' ls-toast--err',
  };

  //: 当前 toast 的状态（容器复用 + 同文案去重：轮询页每 5s 重报同一错误时不刷新闪烁）。
  const current = { node: null, message: '', type: '', timer: null };

  /** 取（或懒建）唯一的 toast 容器节点；非浏览器环境返回 null。 */
  function toastHost() {
    if (typeof document === 'undefined' || !document.body) return null;
    if (current.node && current.node.isConnected) return current.node;
    let node = document.getElementById(TOAST_ID);
    if (!node) {
      node = document.createElement('div');
      node.id = TOAST_ID;
      node.setAttribute('role', 'status');
      node.setAttribute('aria-live', 'polite');
      document.body.appendChild(node);
    }
    current.node = node;
    node.className = 'ls-toast';
    return node;
  }

  /**
   * 弹一条共享 toast。
   *
   * @param {string} msg 面向用户的文案（保持中文原话，不在本层加工）
   * @param {{type?: string, timeout?: number}} [options]
   *        type: info(默认) / ok / warn / error；timeout: 停留毫秒数
   * @returns {Element|null} toast 节点（无 DOM 时 null）
   */
  function toast(msg, options) {
    const opts = options || {};
    const type = opts.type === undefined ? 'info' : String(opts.type);
    const text = String(msg == null ? '' : msg);
    const host = toastHost();
    if (!host) return null;

    const timeoutMs = opts.timeout === undefined
      ? (type === 'error' || type === 'err' || type === 'danger' ? ERROR_TIMEOUT_MS : DEFAULT_TIMEOUT_MS)
      : Number(opts.timeout);

    if (current.message === text && current.type === type) {
      // 同文案同类型：只续命不重绘（轮询失败每轮重报时，用户看到的是一条持续提示）。
      if (current.timer) clearTimeout(current.timer);
    } else {
      host.textContent = text;
      host.className = 'ls-toast' + (TOAST_CLASSES[type] || '');
      current.message = text;
      current.type = type;
    }
    host.classList.add('ls-toast--visible');

    if (current.timer) clearTimeout(current.timer);
    current.timer = setTimeout(function () {
      host.classList.remove('ls-toast--visible');
      current.timer = null;
    }, Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS);
    return host;
  }

  /** 错误出口（`LSFeedback.error(...)` ≡ `toast(..., {type:'error'})`，配色走 .ls-toast--err）。 */
  function error(msg, options) {
    return toast(msg, Object.assign({}, options, { type: 'error' }));
  }

  /**
   * 确认对话框（`<dialog>` 模态实现，Promise<boolean>）。
   *
   * 行为约定（可测）：
   *   · Esc 取消（false）/ Enter 确认（true）；
   *   · 初始焦点在**安全选项**（取消）——误触 Enter 也应先被拦住；
   *   · `danger: true` 时确认键用危险样式（破坏性动作必须让用户看清按的是哪颗）；
   *   · 点遮罩 / 直接关闭 = 取消（不把"没回答"当成"同意"）。
   *
   * @param {string} msg 正文
   * @param {{title?: string, danger?: boolean}} [options]
   * @returns {Promise<boolean>} 用户是否确认
   */
  function confirm(msg, options) {
    const opts = options || {};
    if (typeof document === 'undefined' || !document.body) return Promise.resolve(false);

    return new Promise(function (resolve) {
      const dialog = document.createElement('dialog');
      dialog.className = 'ls-confirm' + (opts.danger ? ' ls-confirm--danger' : '');

      const title = document.createElement('h2');
      title.className = 'ls-confirm-title';
      title.textContent = opts.title ? String(opts.title) : '请确认';

      const message = document.createElement('p');
      message.className = 'ls-confirm-message';
      message.textContent = String(msg == null ? '' : msg);

      const actions = document.createElement('div');
      actions.className = 'ls-confirm-actions';

      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'ls-btn ls-confirm-cancel';
      cancelBtn.textContent = '取消';

      const okBtn = document.createElement('button');
      okBtn.type = 'button';
      okBtn.className = 'ls-btn ls-confirm-ok ' + (opts.danger ? 'ls-btn--danger' : 'ls-btn--primary');
      okBtn.textContent = '确定';

      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      dialog.appendChild(title);
      dialog.appendChild(message);
      dialog.appendChild(actions);
      document.body.appendChild(dialog);

      let settled = false;
      function settle(value) {
        if (settled) return;
        settled = true;
        resolve(!!value);
        if (typeof dialog.close === 'function' && dialog.open) {
          try { dialog.close(); } catch (_) { /* 已关闭 */ }
        }
        dialog.remove();
      }

      // Enter 确认：在 dialog 上拦截（preventDefault 阻止焦点按钮被键盘激活，
      // 所以即使焦点在"取消"上，Enter 也只会确认一次，不会把取消当成确认）。
      dialog.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          settle(true);
        } else if (event.key === 'Escape') {
          event.preventDefault();
          settle(false);
        }
      });
      // Esc 的原生路径（部分浏览器先派发 cancel）与任何其它关闭路径都按"取消"处理。
      dialog.addEventListener('cancel', function (event) {
        event.preventDefault();
        settle(false);
      });
      dialog.addEventListener('close', function () { settle(false); });
      dialog.addEventListener('click', function (event) {
        if (event.target === dialog) settle(false); // 点遮罩 = 取消
      });
      cancelBtn.addEventListener('click', function () { settle(false); });
      okBtn.addEventListener('click', function () { settle(true); });

      if (typeof dialog.showModal === 'function') {
        dialog.showModal();
      } else {
        dialog.setAttribute('open', '');   // 老引擎兜底：降级为非模态，不阻塞页面
      }
      cancelBtn.focus();   // 初始焦点在安全选项（取消）
    });
  }

  return {
    TOAST_ID: TOAST_ID,
    toast: toast,
    error: error,
    confirm: confirm,
  };
});
