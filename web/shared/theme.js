// 前端主题（**唯一实现**）：偏好模型（system/light/dark）+ presenter 投影 + iframe 继承。
//
// ## 架构参考：dsh（deepseek-harness）ui-theme 插件 + theme-presenter
//
// dsh 的做法（packages/client/ui-theme + ui-layout/theme-presenter）：
//   · 主题是**一个插件**：偏好（light/dark/system）由 Host 持久化，index render 时
//     以「head 引导 CSS + body 脚本」注入每个页面——首帧不闪烁；
//   · **单一 presenter** 把解析后的 palette 投影到 DOM（html color-scheme、
//     body[data-ds-dark-theme]、meta theme-color、Electron preload 转发
//     nativeTheme），而不是每个页面各自声明主题；
//   · 桌面与 Web 同一真值。
//
// 本文件是**静态无构建版的同一模式**（00_know/06 §E 追记 2026-10-13：暗色重新
// 激活的前置条件 = Phase II 内容页 token 化完成，已就绪）：
//   · 偏好持久化 = localStorage `ls-theme`（同源共享 ⇒ 壳与全部 iframe 页同一真值，
//     等价于 dsh 的「服务端按当前偏好注入每个 index」）；
//   · presenter = apply()：写 <html data-theme>（tokens 的唯一开关，
//     shared/ui.css :root[data-theme="dark"]）+ meta[name=theme-color] +
//     Electron nativeTheme（桌面端静默跳过）；
//   · 首帧不闪烁 = 各页 <head> 内联引导片段（先于样式表执行，与本文件同一真值）；
//   · iframe 继承 = 壳切换时 postMessage（legged-studio:theme）通知已加载子帧，
//     新加载帧由 head 引导片段自行落地——两条路径覆盖「切换时已打开」与「切换后打开」。
//
// 令牌口径：tokens 唯一真值 = web/shared/ui.css（--ls-*）；workbench.css /
// play-overrides.css / sim2sim 的暗色块全部同值派生，不维护第二套组件。
(function () {
  var KEY = 'ls-theme';
  var MODES = ['system', 'light', 'dark'];
  var LABELS = { system: '跟随系统', light: '浅色', dark: '深色' };
  var ICONS = { system: '🌓', light: '☀️', dark: '🌙' };
  // 画布底色（= --ls-bg 两态；仅用于 meta theme-color 与首帧前背景，不参与规则）
  var CANVAS = { light: '#f4f6f8', dark: '#0b0e13' };

  var mql = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function read() {
    try {
      var v = localStorage.getItem(KEY);
      return MODES.indexOf(v) >= 0 ? v : 'system';
    } catch (e) { return 'system'; }
  }

  function write(mode) {
    try { localStorage.setItem(KEY, mode); } catch (e) { /* 隐私模式：仅本次会话生效 */ }
  }

  function resolve(mode) {
    if (mode === 'dark') return 'dark';
    if (mode === 'light') return 'light';
    return mql && mql.matches ? 'dark' : 'light';
  }

  function setMeta(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head.appendChild(meta);
    }
    meta.content = CANVAS[theme];
  }

  // presenter：把偏好投影到 DOM。notify = 是否广播给同源子帧（壳切换时广播；
  // 帧内跟随广播时不二次广播，避免环路）。
  function apply(mode, options) {
    var notify = !options || options.notify !== false;
    var theme = resolve(mode);
    document.documentElement.dataset.theme = theme;
    setMeta(theme);
    // Electron 原生 chrome（nativeTheme.themeSource）——桌面端专属，Web 下静默跳过
    if (window.leggedStudio && typeof window.leggedStudio.setThemeSource === 'function') {
      try { window.leggedStudio.setThemeSource(mode); } catch (e) { /* 非 Electron 忽略 */ }
    }
    if (notify) {
      var frames = window.frames || [];
      for (var i = 0; i < frames.length; i++) {
        try {
          frames[i].postMessage({ type: 'legged-studio:theme', mode: mode, theme: theme }, window.location.origin);
        } catch (e) { /* 跨域或已卸载帧：忽略 */ }
      }
    }
    return theme;
  }

  function cycle() {
    var mode = MODES[(MODES.indexOf(read()) + 1) % MODES.length];
    write(mode);
    var theme = apply(mode);
    return { mode: mode, theme: theme };
  }

  // 跨帧消息：任一帧落地新偏好后，其余帧（含壳）跟随。origin 限定同源。
  window.addEventListener('message', function (event) {
    if (event.origin !== window.location.origin) return;
    var data = event.data;
    if (!data || data.type !== 'legged-studio:theme') return;
    if (MODES.indexOf(data.mode) >= 0) {
      write(data.mode);
      apply(data.mode, { notify: false });
    } else if (data.theme) {
      document.documentElement.dataset.theme = data.theme;
      setMeta(data.theme);
    }
  });

  // 系统偏好变化：system 模式下实时跟随（无需重新加载）
  if (mql && typeof mql.addEventListener === 'function') {
    mql.addEventListener('change', function () {
      if (read() === 'system') apply('system', { notify: false });
    });
  }

  window.LSTheme = {
    KEY: KEY,
    MODES: MODES,
    LABELS: LABELS,
    ICONS: ICONS,
    CANVAS: CANVAS,
    read: read,
    resolve: resolve,
    apply: apply,
    cycle: cycle,
    write: write,
  };

  // 脚本兜底再应用一次（head 引导片段已设过；此处补齐 meta/nativeTheme/广播），
  // 并让「壳先于 iframe 加载」的场景下，后加载的帧从 localStorage 拿到同一真值。
  apply(read(), { notify: false });
})();
