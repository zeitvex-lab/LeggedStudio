// 前端统一顶栏（**唯一实现**）：品牌 + 8 项功能导航 + 控制面状态点，只在这里写一遍。
//
// ## 为什么要它
//
// 此前 4 个页面各写一套内联顶栏（training_create / training_list /
// training_monitor / exports），连"首页"指向都不一致（dashboard.html vs 新壳
// workbench.html），且各自带一份 /health 探测副本。本文件把分类口径钉成与
// workbench 侧栏同一套（首页 / 机器人工作台 / 训练配置 / 训练任务 / 基础仿真 /
// 高级仿真 / 部署 / 策略档案），当前项高亮由调用方传 `current` 决定。
//
// ## 加载方式（与 shared/api.js 同款 UMD）
//
// 普通脚本（`web/*.html` 的 `<script src="shared/topnav.js">`）→
// `window.LSTopNav.render('lsTopNav', 'training_list.html')`；
// node 侧（测试 / 自检）→ `require('./topnav.js')`，`navHtml()` 是纯字符串函数。
//
// 样式全在 shared/ui.css 的 `.ls-topnav*`（本文件不写任何内联样式）。
(function (root, factory) {
  const topnav = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = topnav;
  } else {
    root.LSTopNav = topnav;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  //: 与 workbench 侧栏同一套分类（分组：工作台 / 机器人 / 训练 / 仿真 / 产物）。
  const NAV_ITEMS = [
    { key: 'home', label: '首页', href: 'workbench.html#home' },
    { key: 'robot', label: '机器人工作台', href: 'workbench.html#robot' },
    { key: 'config', label: '训练配置', href: 'training_create.html' },
    { key: 'training', label: '训练任务', href: 'training_list.html' },
    { key: 'simulation', label: '基础仿真', href: 'workbench.html#simulation' },
    { key: 'navmap', label: '高级仿真', href: 'advanced_sim.html' },
    { key: 'deploy', label: '部署', href: 'deploy.html' },
    { key: 'artifacts', label: '策略档案', href: 'artifacts.html' },
  ];

  const NAV_HTML_ID = 'lsTopNav';
  const STATUS_ID = 'lsTopNavStatus';

  /** 当前项判定：接受 `key`（'training'）、文件名（'training_list.html'）或带锚点的文件名。 */
  function isCurrent(item, current) {
    const value = current == null ? '' : String(current).trim();
    if (!value) return false;
    const parts = value.split('#');
    const file = parts[0];
    const hash = parts[1] || '';
    const itemFile = item.href.split('#')[0];
    const itemHash = (item.href.split('#')[1] || '');
    if (value.indexOf('#') >= 0) return itemFile === file && itemHash === hash;
    if (value.indexOf('.html') >= 0) return itemFile === file;
    return item.key === value;
  }

  /** 未传 current 时的兜底：按当前地址的 文件名[#锚点] 判定。 */
  function currentFromLocation() {
    if (typeof location === 'undefined' || !location) return '';
    const file = String(location.pathname || '').split('/').pop();
    const hash = String(location.hash || '').replace(/^#/, '');
    return hash ? file + '#' + hash : file;
  }

  /** 服务端面板注册表（v2.1 插件化）：/api/panels 的导航投影覆盖 NAV_ITEMS。
   *  拉取失败（后端未起/file://）⇒ 静态 NAV_ITEMS 原样兜底（诚实降级，不假跑）。 */
  function applyRegistryNav(nav) {
    if (!Array.isArray(nav) || !nav.length) return;
    NAV_ITEMS.length = 0;
    for (const item of nav) {
      NAV_ITEMS.push({
        key: item.id,
        label: item.title,
        href: item.href,
        disabled: Boolean(item.disabled),
        disabledReason: item.disabled_reason || '',
      });
    }
  }

  function refreshFromRegistry() {
    if (typeof fetch !== 'function') return;
    try {
      fetch('/api/panels', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (payload) {
          if (payload && Array.isArray(payload.navigation)) applyRegistryNav(payload.navigation);
        })
        .catch(function () { /* 静态清单兜底（诚实降级） */ });
    } catch (e) { /* 环境无 fetch */ }
  }

  /** 纯字符串视图（node 可测；页面渲染即 innerHTML 这一次赋值）。 */
  function navHtml(current) {
    const items = NAV_ITEMS.map(function (item, index) {
      const active = isCurrent(item, current);
      const indexText = String(index + 1).padStart(2, '0');
      // 高亮用 aria-current="true"（"集合中的当前项"）：训练监控这类**子页**会刻意
      // 高亮它的父类目，写 "page" 就成了"本页即训练任务列表"的假陈述。
      return '<a class="ls-nav-item' + (active ? ' is-current' : '') + '" href="' + item.href + '"'
        + (active ? ' aria-current="true"' : '') + '>'
        + '<span class="ls-nav-index">' + indexText + '</span>' + item.label + '</a>';
    }).join('');
    return '<a class="ls-brand" href="workbench.html#home" aria-label="Legged Studio 首页">'
      + '<span class="ls-brand-mark">LS</span>'
      + '<span class="ls-brand-text"><strong>Legged Studio</strong><small>Robotics Workbench</small></span>'
      + '</a>'
      + '<nav class="ls-nav" aria-label="主功能">' + items + '</nav>'
      + '<span class="ls-topnav-status" id="' + STATUS_ID + '" title="控制面状态探测中">'
      + '<i></i><span>控制面…</span></span>';
  }

  /** 控制面状态点：/health 一次探测（失败只变灰红，不抛错、不写 console）。
   *  嵌入态（workbench iframe）顶栏整体隐藏，没必要再探一次。 */
  function probeControlPlane(host) {
    const box = host.querySelector('.ls-topnav-status');
    if (!box || typeof fetch !== 'function') return null;
    if (document.body && document.body.classList.contains('embedded')) return null;
    const base = (typeof location !== 'undefined' && /^https?:$/.test(location.protocol))
      ? location.origin
      : 'http://127.0.0.1:8765';
    const paint = function (ok) {
      box.classList.toggle('is-ok', ok);
      box.classList.toggle('is-err', !ok);
      const label = box.querySelector('span');
      if (label) label.textContent = ok ? '控制面在线' : '控制面离线';
      box.title = ok ? '控制面 /health 在线' : '控制面 /health 不可达';
    };
    return fetch(base + '/health')
      .then(function (response) { paint(!!response.ok); })
      .catch(function () { paint(false); });
  }

  /**
   * 渲染顶栏。
   *
   * **挂载点元素本身就是顶栏**（`<header id="lsTopNav"></header>`）：sticky 的粘性
   * 范围取决于自身盒模型，若再套一层空 wrapper，顶栏滚两下就会脱粘。
   *
   * @param {string} mountId 挂载点元素 id（页面里按旧顶栏的位置放一个空 header）
   * @param {string} [current] 当前项（key / 文件名）；缺省按地址推导
   * @returns {Element|null} 挂载点；找不到挂载点返回 null（页面照常工作）
   */
  function render(mountId, current) {
    if (typeof document === 'undefined') return null;
    const host = document.getElementById(mountId || NAV_HTML_ID);
    if (!host) return null;
    const active = current == null || current === '' ? currentFromLocation() : current;
    host.classList.add('ls-topnav');
    if (host.tagName !== 'HEADER') host.setAttribute('role', 'banner');
    host.innerHTML = navHtml(active);
    probeControlPlane(host);
    return host;
  }

  return {
    NAV_ITEMS: NAV_ITEMS,
    NAV_HTML_ID: NAV_HTML_ID,
    STATUS_ID: STATUS_ID,
    isCurrent: isCurrent,
    navHtml: navHtml,
    render: render,
    applyRegistryNav: applyRegistryNav,
    refreshFromRegistry: refreshFromRegistry,
  };
});
