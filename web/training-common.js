/**
 * Legged Studio - Training UI shared helpers.
 *
 * Used exclusively by training_create.html / training_list.html /
 * training_monitor.html. Vanilla JS only, no build step, fully offline.
 *
 * Patterns borrowed from the studied references:
 * - smoothMetricSeries / metric windowing  (references_1000framesai site/train_app.js)
 * - multi-series live line charts with grid, axis labels and legend
 *   (ReinforceUI-Studio GUI/ui_utils.py PlotCanvas + wandb run charts)
 * - stick-to-bottom-only-if-near-bottom log scrolling (train_app.js renderLog)
 */
(function (global) {
  'use strict';

  // When the pages are served by the control plane (FastAPI StaticFiles at
  // /web/...) the API lives on the same origin. Fall back to the well-known
  // desktop control-plane port for file:// usage.
  const API_BASE = (global.location && /^https?:$/.test(global.location.protocol))
    ? global.location.origin
    : 'http://127.0.0.1:8765';

  const CHART_COLORS = [
    '#2dd4bf', '#60a5fa', '#f59e0b', '#f472b6', '#a78bfa',
    '#34d399', '#fb7185', '#38bdf8', '#facc15', '#c084fc',
  ];

  /**
   * Run-level color palette (wandb-style). Paired with runColor(key) below so
   * a run/series key always maps to the same color regardless of insertion
   * order — adding a new metric never reshuffles the existing colors.
   */
  const RUN_COLORS = [
    '#2dd4bf', '#60a5fa', '#f59e0b', '#f472b6', '#a78bfa', '#34d399',
    '#fb7185', '#38bdf8', '#facc15', '#c084fc', '#4ade80', '#e879f9',
  ];

  /** Deterministic 32-bit string hash (djb2). */
  function hashString(value) {
    const str = String(value == null ? '' : value);
    let h = 5381;
    for (let i = 0; i < str.length; i += 1) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  /** Stable color for a key inside a palette (defaults to RUN_COLORS). */
  function runColor(key, palette) {
    const colors = Array.isArray(palette) && palette.length ? palette : RUN_COLORS;
    return colors[hashString(key) % colors.length];
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function stripAnsi(value) {
    return String(value == null ? '' : value).replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
  }

  /** Adaptive number formatting for metric readouts (train_app.js fmtMetric). */
  function fmtMetric(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    const abs = Math.abs(n);
    if (abs >= 1e6 || (abs > 0 && abs < 1e-4)) return n.toExponential(3);
    if (abs >= 1000) return n.toFixed(0);
    if (abs >= 100) return n.toFixed(1);
    if (abs >= 1) return n.toFixed(3).replace(/\.?0+$/, '');
    if (abs === 0) return '0';
    return n.toFixed(4).replace(/\.?0+$/, '');
  }

  /** Compact axis tick formatting (train_app.js fmtAxis). */
  function fmtAxis(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '-';
    const abs = Math.abs(n);
    if (abs >= 1e6 || (abs > 0 && abs < 1e-3)) return n.toExponential(1);
    if (abs >= 1000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'k';
    if (abs >= 10) return n.toFixed(0);
    if (abs >= 1) return n.toFixed(1);
    if (abs === 0) return '0';
    return n.toFixed(3).replace(/\.?0+$/, '');
  }

  function fmtDuration(seconds) {
    const s = Number(seconds);
    if (!Number.isFinite(s) || s < 0) return '-';
    if (s < 1) return '<1s';
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
  }

  function fmtBytes(bytes) {
    const n = Number(bytes);
    if (!Number.isFinite(n) || n < 0) return '-';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  /** "3 分钟前" style relative time for ISO strings. */
  function fmtRelativeTime(iso) {
    if (!iso) return '-';
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return String(iso);
    const delta = Math.max(0, Date.now() - t) / 1000;
    if (delta < 10) return '刚刚';
    if (delta < 60) return `${Math.floor(delta)} 秒前`;
    if (delta < 3600) return `${Math.floor(delta / 60)} 分钟前`;
    if (delta < 86400) return `${Math.floor(delta / 3600)} 小时前`;
    return `${Math.floor(delta / 86400)} 天前`;
  }

  function fmtDateTime(iso) {
    if (!iso) return '-';
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return String(iso);
    const d = new Date(t);
    const pad = (v) => String(v).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  /** Status badge mapping covering every backend status value. */
  const STATUS_MAP = {
    pending: { label: '等待中', cls: 'pending' },
    running: { label: '运行中', cls: 'running' },
    completed: { label: '已完成', cls: 'completed' },
    failed: { label: '失败', cls: 'failed' },
    stopped: { label: '已停止', cls: 'stopped' },
  };

  function statusInfo(status) {
    const key = String(status || '').toLowerCase();
    if (STATUS_MAP[key]) return STATUS_MAP[key];
    // Older workers wrote statuses like "train_completed".
    if (key.endsWith('completed')) return { label: '已完成', cls: 'completed' };
    if (key.includes('fail') || key.includes('error')) return { label: '失败', cls: 'failed' };
    if (key.includes('stop') || key.includes('cancel')) return { label: '已停止', cls: 'stopped' };
    return { label: String(status || '未知'), cls: 'unknown' };
  }

  function statusBadge(status) {
    const info = statusInfo(status);
    const breathe = info.cls === 'running' || info.cls === 'pending' ? ' tsui-breathe' : '';
    return `<span class="status-badge ${info.cls}" title="${escapeHtml(status)}"><span class="status-dot${breathe}"></span>${escapeHtml(info.label)}</span>`;
  }

  // ---------- 共享状态点样式（breathing dot） ----------
  // 由各页面通过 ensureSharedStyles() 注入一次；训练列表/监控页的状态点
  // 共用同一组颜色约定：绿=运行中 / 蓝=已完成 / 红=失败 / 灰=停止·等待。
  const SHARED_STYLE_ID = 'tsui-shared-styles';

  function ensureSharedStyles() {
    if (typeof document === 'undefined' || !document.head) return;
    if (document.getElementById(SHARED_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = SHARED_STYLE_ID;
    style.textContent = [
      '@keyframes tsui-breathe { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }',
      '.tsui-breathe { animation: tsui-breathe 1.5s ease-in-out infinite; }',
      '.tsui-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #94a3b8; flex-shrink: 0; }',
      '.tsui-dot.running { background: #2dd4bf; }',
      '.tsui-dot.completed { background: #60a5fa; }',
      '.tsui-dot.failed { background: #f87171; }',
      '.tsui-dot.stopped, .tsui-dot.pending, .tsui-dot.unknown, .tsui-dot.idle { background: #94a3b8; }',
    ].join('\n');
    document.head.appendChild(style);
  }

  /**
   * Colored state dot HTML (wandb run-state convention): green running /
   * blue completed / red failed / gray stopped or pending. The dot breathes
   * (1.5s opacity keyframe) while the run is live unless options.breathe
   * says otherwise.
   */
  function statusDotHtml(status, options) {
    const opts = options || {};
    const info = statusInfo(status);
    const breathe = opts.breathe == null
      ? (info.cls === 'running' || info.cls === 'pending')
      : !!opts.breathe;
    return `<span class="tsui-dot ${info.cls}${breathe ? ' tsui-breathe' : ''}" title="${escapeHtml(status == null ? '' : status)}"></span>`;
  }

  /**
   * Flatten nested objects into dotted key paths (a.b.c). Plain objects are
   * recursed; arrays and primitives are kept as leaf values.
   */
  function flattenDict(value, prefix, out) {
    const result = out || {};
    const base = prefix || '';
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.keys(value).forEach((key) => {
        const path = base ? `${base}.${key}` : key;
        const child = value[key];
        if (child && typeof child === 'object' && !Array.isArray(child)) flattenDict(child, path, result);
        else result[path] = child;
      });
    } else if (base) {
      result[base] = value;
    }
    return result;
  }

  /**
   * Moving-average smoothing (train_app.js smoothMetricSeries): the smoothed
   * value at index i is the mean of the trailing `size` raw values.
   */
  function smoothSeries(points, windowSize) {
    const size = Math.max(1, Math.floor(Number(windowSize) || 1));
    if (size === 1) return points;
    const out = new Array(points.length);
    let sum = 0;
    for (let i = 0; i < points.length; i += 1) {
      sum += points[i].y;
      if (i >= size) sum -= points[i - size].y;
      const count = Math.min(i + 1, size);
      out[i] = { x: points[i].x, y: sum / count };
    }
    return out;
  }

  /**
   * Tracks (value, timestamp) samples and derives an iteration speed and ETA.
   * Duplicate values (polls between worker updates) are ignored.
   */
  class RateTracker {
    constructor(maxSamples = 10) {
      this.maxSamples = maxSamples;
      this.samples = [];
    }

    push(value, timestamp) {
      const v = Number(value);
      if (!Number.isFinite(v)) return;
      const t = timestamp == null ? Date.now() : timestamp;
      const last = this.samples[this.samples.length - 1];
      if (last && last.v === v) return;
      this.samples.push({ v, t });
      if (this.samples.length > this.maxSamples) this.samples.shift();
    }

    /** Units per second over the observed window, or null. */
    rate() {
      if (this.samples.length < 2) return null;
      const first = this.samples[0];
      const last = this.samples[this.samples.length - 1];
      const dt = (last.t - first.t) / 1000;
      const dv = last.v - first.v;
      if (dt <= 0 || dv <= 0) return null;
      return dv / dt;
    }

    /** Seconds to reach target from the latest value, or null. */
    eta(target) {
      const rate = this.rate();
      const last = this.samples[this.samples.length - 1];
      if (rate == null || !last || Number(last.v) >= Number(target)) return null;
      return (Number(target) - last.v) / rate;
    }

    reset() { this.samples = []; }
  }

  /**
   * Canvas multi-series line chart with grid, axis labels, crosshair hover and
   * a drawn tooltip. HiDPI aware, redraws on container resize.
   */
  class TrainingChart {
    constructor(canvas, options = {}) {
      if (!canvas) throw new Error('TrainingChart requires a canvas element');
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.options = Object.assign({
        xLabel: '迭代',
        yLabel: '',
        pad: { left: 58, right: 18, top: 14, bottom: 30 },
        gridColor: 'rgba(148, 163, 184, 0.14)',
        axisColor: 'rgba(148, 163, 184, 0.35)',
        textColor: '#94a3b8',
        emptyText: '暂无曲线数据',
        font: '11px ui-monospace, SFMono-Regular, Consolas, monospace',
      }, options);
      this.series = [];   // [{name, color, points, visible}]
      this.hover = null;  // css-pixel coordinates inside the canvas box
      this._onMove = this._onMove.bind(this);
      this._onLeave = this._onLeave.bind(this);
      canvas.addEventListener('mousemove', this._onMove);
      canvas.addEventListener('mouseleave', this._onLeave);
      if (global.ResizeObserver) {
        this._ro = new ResizeObserver(() => this.draw());
        this._ro.observe(canvas);
      }
    }

    /** series: [{name, points:[{x,y}], visible?, color?}] */
    setSeries(series) {
      this.series = (series || []).map((item, index) => ({
        name: item.name || `series-${index}`,
        color: item.color || CHART_COLORS[index % CHART_COLORS.length],
        points: Array.isArray(item.points) ? item.points : [],
        visible: item.visible !== false,
      }));
      this.draw();
    }

    setVisible(name, visible) {
      const s = this.series.find((item) => item.name === name);
      if (s) { s.visible = !!visible; this.draw(); }
    }

    _onMove(event) {
      const rect = this.canvas.getBoundingClientRect();
      this.hover = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      this.draw();
    }

    _onLeave() {
      this.hover = null;
      this.draw();
    }

    _plotArea() {
      const w = this.canvas.clientWidth || 360;
      const h = this.canvas.clientHeight || 220;
      const p = this.options.pad;
      return { x: p.left, y: p.top, w: Math.max(10, w - p.left - p.right), h: Math.max(10, h - p.top - p.bottom), cw: w, ch: h };
    }

    draw() {
      const canvas = this.canvas;
      const dpr = global.devicePixelRatio || 1;
      const cssW = canvas.clientWidth || 360;
      const cssH = canvas.clientHeight || 220;
      if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
      }
      const ctx = this.ctx;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);

      const area = this._plotArea();
      const visible = this.series.filter((s) => s.visible && s.points.length);
      ctx.font = this.options.font;
      ctx.fillStyle = this.options.textColor;

      // Axes frame
      ctx.strokeStyle = this.options.axisColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(area.x + 0.5, area.y);
      ctx.lineTo(area.x + 0.5, area.y + area.h + 0.5);
      ctx.lineTo(area.x + area.w, area.y + area.h + 0.5);
      ctx.stroke();

      if (!visible.length) {
        ctx.fillStyle = '#475569';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(this.options.emptyText, area.x + area.w / 2, area.y + area.h / 2);
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';
        return;
      }

      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const s of visible) {
        for (const pt of s.points) {
          if (pt.x < minX) minX = pt.x;
          if (pt.x > maxX) maxX = pt.x;
          if (Number.isFinite(pt.y)) {
            if (pt.y < minY) minY = pt.y;
            if (pt.y > maxY) maxY = pt.y;
          }
        }
      }
      if (minX === maxX) { maxX = minX + 1; }
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const yPad = (maxY - minY) * 0.08;
      minY -= yPad; maxY += yPad;

      const xFor = (x) => area.x + ((x - minX) / (maxX - minX)) * area.w;
      const yFor = (y) => area.y + (1 - (y - minY) / (maxY - minY)) * area.h;

      // Horizontal grid + y tick labels (5 ticks, wandb-style guide lines).
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let i = 0; i <= 4; i += 1) {
        const value = minY + ((maxY - minY) * i) / 4;
        const y = yFor(value);
        ctx.strokeStyle = this.options.gridColor;
        ctx.beginPath();
        ctx.moveTo(area.x + 1, Math.round(y) + 0.5);
        ctx.lineTo(area.x + area.w, Math.round(y) + 0.5);
        ctx.stroke();
        ctx.fillStyle = this.options.textColor;
        ctx.fillText(fmtAxis(value), area.x - 8, y);
      }

      // X tick labels (5 ticks).
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      for (let i = 0; i <= 4; i += 1) {
        const value = minX + ((maxX - minX) * i) / 4;
        const x = xFor(value);
        const label = i === 0 ? fmtAxis(minX) : (i === 4 ? fmtAxis(maxX) : fmtAxis(Math.round(value)));
        ctx.fillStyle = this.options.textColor;
        ctx.fillText(label, Math.min(Math.max(x, area.x + 14), area.x + area.w - 14), area.y + area.h + 7);
      }

      // Axis labels
      if (this.options.yLabel) {
        ctx.save();
        ctx.translate(12, area.y + area.h / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(this.options.yLabel, 0, 0);
        ctx.restore();
      }
      if (this.options.xLabel) {
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(this.options.xLabel, area.x + area.w, area.ch - 1);
      }

      // Series lines
      for (const s of visible) {
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.beginPath();
        let started = false;
        for (const pt of s.points) {
          if (!Number.isFinite(pt.y)) continue;
          const px = xFor(pt.x);
          const py = yFor(pt.y);
          if (!started) { ctx.moveTo(px, py); started = true; }
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
        // End marker on the newest point.
        const lastPt = [...s.points].reverse().find((pt) => Number.isFinite(pt.y));
        if (lastPt && s.points.length > 1) {
          ctx.fillStyle = s.color;
          ctx.beginPath();
          ctx.arc(xFor(lastPt.x), yFor(lastPt.y), 3, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      if (this.hover) this._drawHover(ctx, area, { minX, maxX, minY, maxY, xFor, yFor, visible });
    }

    _drawHover(ctx, area, scale) {
      const { hover } = this;
      if (hover.x < area.x || hover.x > area.x + area.w || hover.y < area.y || hover.y > area.y + area.h) return;

      // Crosshair at the nearest sampled x across visible series.
      const hoverX = scale.minX + ((hover.x - area.x) / area.w) * (scale.maxX - scale.minX);
      let nearest = null;
      for (const s of scale.visible) {
        for (const pt of s.points) {
          if (!Number.isFinite(pt.y)) continue;
          if (!nearest || Math.abs(pt.x - hoverX) < Math.abs(nearest.x - hoverX)) {
            nearest = { x: pt.x, y: pt.y };
          }
        }
      }
      if (!nearest) return;

      const cx = scale.xFor(nearest.x);
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.5)';
      ctx.setLineDash([4, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(cx) + 0.5, area.y);
      ctx.lineTo(Math.round(cx) + 0.5, area.y + area.h);
      ctx.stroke();
      ctx.setLineDash([]);

      // Tooltip rows: value of every series at the nearest x of each series.
      const rows = [];
      for (const s of scale.visible) {
        let best = null;
        for (const pt of s.points) {
          if (!Number.isFinite(pt.y)) continue;
          if (!best || Math.abs(pt.x - nearest.x) < Math.abs(best.x - nearest.x)) best = pt;
        }
        if (best) {
          ctx.fillStyle = s.color;
          ctx.beginPath();
          ctx.arc(scale.xFor(best.x), scale.yFor(best.y), 3.5, 0, Math.PI * 2);
          ctx.fill();
          rows.push({ name: s.name, value: best.y, color: s.color });
        }
      }

      ctx.font = this.options.font;
      const title = `迭代 ${fmtAxis(nearest.x)}`;
      const lines = [title].concat(rows.map((r) => `${r.name}: ${fmtMetric(r.value)}`));
      const textW = Math.max(...lines.map((line) => ctx.measureText(line).width));
      const boxW = textW + 20;
      const boxH = lines.length * 16 + 10;
      let bx = cx + 12;
      let by = area.y + 8;
      if (bx + boxW > area.x + area.w) bx = cx - boxW - 12;
      if (by + boxH > area.ch) by = Math.max(area.y, area.ch - boxH - 4);

      ctx.fillStyle = 'rgba(10, 13, 16, 0.92)';
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(bx, by, boxW, boxH, 6) : ctx.rect(bx, by, boxW, boxH);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#cbd5e1';
      ctx.fillText(title, bx + 10, by + 6);
      rows.forEach((row, index) => {
        const y = by + 22 + index * 16;
        ctx.fillStyle = row.color;
        ctx.fillRect(bx + 10, y + 3, 8, 8);
        ctx.fillStyle = '#e2e8f0';
        ctx.fillText(`${row.name}: ${fmtMetric(row.value)}`, bx + 24, y);
      });
    }

    destroy() {
      if (this._ro) this._ro.disconnect();
      this.canvas.removeEventListener('mousemove', this._onMove);
      this.canvas.removeEventListener('mouseleave', this._onLeave);
    }
  }

  /** fetch() JSON helper with a consistent error message. */
  async function fetchJson(path, init) {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body && body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      } catch (err) { /* non-JSON error body */ }
      throw new Error(detail);
    }
    return response.json();
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  ensureSharedStyles();

  global.TrainingUI = {
    API_BASE,
    CHART_COLORS,
    RUN_COLORS,
    TrainingChart,
    RateTracker,
    escapeHtml,
    stripAnsi,
    fmtMetric,
    fmtAxis,
    fmtDuration,
    fmtBytes,
    fmtRelativeTime,
    fmtDateTime,
    statusInfo,
    statusBadge,
    statusDotHtml,
    smoothSeries,
    fetchJson,
    downloadText,
    hashString,
    runColor,
    flattenDict,
    ensureSharedStyles,
  };
})(window);
