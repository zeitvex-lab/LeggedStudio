import { billing, payments } from "/shared/api.js?v=wallet-custom-1";
import { mountNav, requireAuth } from "/shared/nav.js?v=home-nav-1";

const POLL_INTERVAL_MS = 2000;
const STATUS = {
  checking: ["检查中", "checking"],
  ready: ["可充值", "ready"],
  creating: ["创建中", "creating"],
  pending: ["待支付", "pending"],
  paid: ["已到账", "paid"],
  expired: ["已过期", "expired"],
  closed: ["已关闭", "closed"],
  failed: ["支付失败", "failed"],
  unavailable: ["未开放", "unavailable"],
};
const TERMINAL_STATUSES = new Set(["paid", "expired", "closed", "failed", "canceled"]);
const KIND_LABEL = {
  topup: "充值",
  recharge: "微信支付充值",
  wechat_topup: "微信支付充值",
  wechat_pay: "微信支付充值",
  wechat_payment: "微信支付充值",
  wechat_native: "微信支付充值",
  payment: "微信支付充值",
  freeze: "启动保留",
  charge: "训练实时扣费",
  settle: "结算退还",
  refund: "退还",
  adjust: "调整",
};

const el = {
  balance: document.getElementById("balance"),
  username: document.getElementById("username"),
  amountOptions: document.getElementById("amountOptions"),
  customAmount: document.getElementById("customAmount"),
  customAmountHint: document.getElementById("customAmountHint"),
  createPayment: document.getElementById("createPaymentBtn"),
  paymentMessage: document.getElementById("paymentMessage"),
  paymentStatus: document.getElementById("paymentStatus"),
  paymentEmpty: document.getElementById("paymentEmpty"),
  paymentEmptyTitle: document.getElementById("paymentEmptyTitle"),
  paymentEmptyDetail: document.getElementById("paymentEmptyDetail"),
  paymentOrder: document.getElementById("paymentOrder"),
  paymentQrFrame: document.getElementById("paymentQrFrame"),
  paymentQr: document.getElementById("paymentQr"),
  paymentResult: document.getElementById("paymentResult"),
  paymentResultTitle: document.getElementById("paymentResultTitle"),
  paymentResultDetail: document.getElementById("paymentResultDetail"),
  paymentAmount: document.getElementById("paymentAmount"),
  paymentCountdown: document.getElementById("paymentCountdown"),
  paymentOrderId: document.getElementById("paymentOrderId"),
  retryPayment: document.getElementById("retryPaymentBtn"),
  txnBody: document.getElementById("txnBody"),
  txnEmpty: document.getElementById("txnEmpty"),
  refresh: document.getElementById("refreshBtn"),
};

const state = {
  enabled: false,
  amounts: [],
  minAmount: 100,
  maxAmount: 5_000_000,
  selectedAmount: null,
  order: null,
  creating: false,
  pollTimer: null,
  countdownTimer: null,
  pollInFlight: false,
  creditedOrderId: null,
};

function fmtYuan(cents) {
  const value = Number(cents || 0) / 100;
  return `${value < 0 ? "-" : ""}¥${Math.abs(value).toFixed(2)}`;
}

function fmtDate(timestamp) {
  const milliseconds = toMilliseconds(timestamp);
  if (!milliseconds) return "-";
  try {
    return new Date(milliseconds).toLocaleString("zh-CN");
  } catch {
    return "-";
  }
}

function toMilliseconds(timestamp) {
  if (timestamp === null || timestamp === undefined || timestamp === "") return 0;
  if (typeof timestamp === "number" || /^\d+(\.\d+)?$/.test(String(timestamp))) {
    const numeric = Number(timestamp);
    if (!Number.isFinite(numeric)) return 0;
    return numeric < 1e12 ? numeric * 1000 : numeric;
  }
  const parsed = Date.parse(String(timestamp));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]
  ));
}

function normalizeStatus(value) {
  const status = String(value || "pending").toLowerCase();
  if (["success", "succeeded", "credited"].includes(status)) return "paid";
  if (["cancelled", "revoked"].includes(status)) return "canceled";
  return STATUS[status] ? status : "pending";
}

function setPaymentStatus(status) {
  const normalized = STATUS[status] ? status : "checking";
  const [label, className] = STATUS[normalized];
  el.paymentStatus.textContent = label;
  el.paymentStatus.className = `wallet-status ${className}`;
}

function setMessage(message = "", type = "") {
  el.paymentMessage.textContent = message;
  el.paymentMessage.className = `wallet-message${type ? ` ${type}` : ""}`;
}

function showPaymentEmpty(title, detail, status = "ready") {
  el.paymentOrder.hidden = true;
  el.paymentEmpty.hidden = false;
  el.paymentEmptyTitle.textContent = title;
  el.paymentEmptyDetail.textContent = detail;
  setPaymentStatus(status);
}

function isPendingOrder() {
  return state.order && !TERMINAL_STATUSES.has(normalizeStatus(state.order.status));
}

function updateControls() {
  const locked = state.creating || isPendingOrder();
  for (const button of el.amountOptions.querySelectorAll("button[data-amount-cents]")) {
    button.disabled = !state.enabled || locked;
  }
  el.customAmount.disabled = !state.enabled || locked;
  el.createPayment.disabled = !state.enabled || !state.selectedAmount || locked;

  if (state.creating) {
    el.createPayment.textContent = "正在生成二维码";
  } else if (isPendingOrder()) {
    el.createPayment.textContent = "等待支付";
  } else if (normalizeStatus(state.order?.status) === "paid") {
    el.createPayment.textContent = "继续充值";
  } else {
    el.createPayment.textContent = "充值并生成微信支付二维码";
  }
}

function amountRangeLabel() {
  return `${fmtYuan(state.minAmount)} - ${fmtYuan(state.maxAmount)}，最多两位小数`;
}

function parseYuanToCents(value) {
  const match = String(value || "").trim().match(/^(\d+)(?:\.(\d{0,2}))?$/);
  if (!match) return null;
  const yuan = Number(match[1]);
  const fraction = Number((match[2] || "").padEnd(2, "0"));
  const cents = yuan * 100 + fraction;
  return Number.isSafeInteger(cents) ? cents : null;
}

function setCustomHint(message = amountRangeLabel(), error = false) {
  el.customAmountHint.textContent = message;
  el.customAmountHint.classList.toggle("error", error);
}

function selectAmount(amountCents, { custom = false } = {}) {
  if (!state.enabled || state.creating || isPendingOrder()) return;
  state.selectedAmount = amountCents;
  if (!custom) el.customAmount.value = "";
  for (const button of el.amountOptions.querySelectorAll("button[data-amount-cents]")) {
    const selected = !custom && Number(button.dataset.amountCents) === amountCents;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-checked", String(selected));
  }
  setCustomHint(custom ? `将充值 ${fmtYuan(amountCents)}` : amountRangeLabel());
  updateControls();
}

function onCustomAmountInput() {
  if (!state.enabled || state.creating || isPendingOrder()) return;
  const raw = el.customAmount.value.trim();
  const amountCents = parseYuanToCents(raw);
  for (const button of el.amountOptions.querySelectorAll("button[data-amount-cents]")) {
    button.classList.remove("selected");
    button.setAttribute("aria-checked", "false");
  }
  state.selectedAmount = null;
  if (!raw) {
    setCustomHint();
  } else if (amountCents === null || amountCents < state.minAmount || amountCents > state.maxAmount) {
    setCustomHint(`请输入 ${amountRangeLabel()}`, true);
  } else {
    selectAmount(amountCents, { custom: true });
  }
  updateControls();
}

function renderAmounts() {
  el.amountOptions.replaceChildren();
  if (!state.amounts.length) {
    const empty = document.createElement("button");
    empty.type = "button";
    empty.className = "wallet-amount wallet-amount-loading";
    empty.disabled = true;
    empty.textContent = "可输入自定义金额";
    el.amountOptions.append(empty);
    updateControls();
    return;
  }

  for (const amount of state.amounts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "wallet-amount";
    button.dataset.amountCents = String(amount);
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", "false");
    button.innerHTML = `${fmtYuan(amount)}${amount === 100 ? "<small>小额测试</small>" : ""}`;
    button.addEventListener("click", () => selectAmount(amount));
    el.amountOptions.append(button);
  }
  selectAmount(state.amounts[0]);
}

function renderTransactions(transactions) {
  if (!transactions.length) {
    el.txnBody.replaceChildren();
    el.txnEmpty.hidden = false;
    return;
  }

  el.txnEmpty.hidden = true;
  el.txnBody.innerHTML = transactions.map((transaction) => {
    const amount = Number(transaction.amount_cents || 0);
    const amountClass = amount >= 0 ? "wallet-credit" : "wallet-debit";
    return `
      <tr>
        <td class="wallet-date">${fmtDate(transaction.created_at)}</td>
        <td>${KIND_LABEL[transaction.kind] || escapeHtml(transaction.kind)}</td>
        <td class="wallet-number ${amountClass}">${fmtYuan(amount)}</td>
        <td class="wallet-number">${fmtYuan(transaction.balance_after_cents)}</td>
        <td class="wallet-note">${escapeHtml(transaction.note)}</td>
      </tr>`;
  }).join("");
}

async function loadWallet() {
  try {
    const wallet = await billing.me();
    el.balance.textContent = fmtYuan(wallet.balance_cents);
    renderTransactions(wallet.transactions || []);
    const navBalance = document.querySelector(".pnav-balance");
    if (navBalance) navBalance.textContent = fmtYuan(wallet.balance_cents);
  } catch (error) {
    el.balance.textContent = "加载失败";
    el.txnEmpty.hidden = true;
    el.txnBody.innerHTML = `<tr><td colspan="5" class="wallet-note">${escapeHtml(error.message)}</td></tr>`;
  }
}

function orderedAmounts(values) {
  const unique = [...new Set((Array.isArray(values) ? values : [])
    .map(Number)
    .filter((value) => Number.isSafeInteger(value) && value > 0))];
  return unique.includes(100) ? [100, ...unique.filter((value) => value !== 100)] : unique;
}

async function loadPaymentConfig() {
  try {
    const config = await payments.wechat.config();
    state.enabled = Boolean(config.enabled);
    state.amounts = orderedAmounts(config.amounts_cents);
    state.minAmount = Number(config.min_amount_cents) || 100;
    state.maxAmount = Number(config.max_amount_cents) || 5_000_000;
    renderAmounts();

    if (!state.enabled) {
      showPaymentEmpty("微信支付暂未开放", "请稍后再试", "unavailable");
      setMessage("当前无法创建支付订单。", "error");
    } else {
      showPaymentEmpty("选择金额并生成二维码", "每个二维码仅对应当前充值订单", "ready");
      setMessage("付款完成后，本页会自动确认到账。", "");
    }
    updateControls();
  } catch (error) {
    state.enabled = false;
    state.amounts = [];
    renderAmounts();
    showPaymentEmpty("支付服务暂不可用", "请稍后刷新页面重试", "unavailable");
    setMessage(error.message, "error");
  }
}

async function recoverPendingPayment() {
  try {
    const result = await payments.wechat.orders();
    if (!result.latest_pending) return;
    await acceptOrder(result.latest_pending);
    startTracking();
  } catch (error) {
    if (state.enabled) setMessage(`未能恢复待支付订单：${error.message}`, "error");
  }
}

function stopTracking() {
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  if (state.countdownTimer) window.clearInterval(state.countdownTimer);
  state.pollTimer = null;
  state.countdownTimer = null;
}

function updateCountdown() {
  if (!isPendingOrder()) return;
  const expiresAt = toMilliseconds(state.order.expires_at);
  if (!expiresAt) {
    el.paymentCountdown.textContent = "以微信订单为准";
    return;
  }
  const remainingSeconds = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  el.paymentCountdown.textContent = remainingSeconds > 0
    ? `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : "正在确认";
}

function renderOrder() {
  if (!state.order) return;
  const status = normalizeStatus(state.order.status);
  el.paymentEmpty.hidden = true;
  el.paymentOrder.hidden = false;
  el.paymentAmount.textContent = fmtYuan(state.order.amount_cents);
  el.paymentOrderId.textContent = state.order.id || "-";
  el.paymentOrderId.title = state.order.id || "";
  setPaymentStatus(status === "canceled" ? "closed" : status);

  const pending = !TERMINAL_STATUSES.has(status);
  el.paymentQrFrame.hidden = !pending;
  el.paymentResult.hidden = pending;
  el.retryPayment.hidden = pending || status === "paid";

  if (pending) {
    el.paymentQr.src = state.order.qr_url || "";
    updateCountdown();
    setMessage("请使用微信扫描二维码完成支付。", "");
  } else {
    el.paymentQr.removeAttribute("src");
    el.paymentCountdown.textContent = status === "paid" ? "已完成" : "已结束";
    const result = {
      paid: ["支付成功", "充值已自动计入当前账户"],
      expired: ["二维码已过期", "请重新生成支付二维码"],
      closed: ["订单已关闭", "请重新生成支付二维码"],
      canceled: ["订单已关闭", "请重新生成支付二维码"],
      failed: ["支付未完成", "请重新生成支付二维码"],
    }[status] || ["订单已结束", "请重新生成支付二维码"];
    el.paymentResultTitle.textContent = result[0];
    el.paymentResultDetail.textContent = result[1];
    setMessage(status === "paid" ? "余额和交易记录已更新。" : result[1], status === "paid" ? "success" : "error");
  }
  updateControls();
}

async function acceptOrder(order) {
  if (!order || !order.id) throw new Error("支付订单响应无效");
  state.order = order;
  renderOrder();

  const status = normalizeStatus(order.status);
  if (status === "paid") {
    stopTracking();
    if (state.creditedOrderId !== order.id) {
      state.creditedOrderId = order.id;
      await loadWallet();
    }
  } else if (TERMINAL_STATUSES.has(status)) {
    stopTracking();
  }
}

function schedulePoll(delay = POLL_INTERVAL_MS) {
  if (!isPendingOrder()) return;
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  state.pollTimer = window.setTimeout(pollOrder, delay);
}

async function pollOrder() {
  if (!isPendingOrder() || state.pollInFlight) return;
  if (document.hidden) {
    schedulePoll();
    return;
  }

  const orderId = state.order.id;
  state.pollInFlight = true;
  try {
    const order = await payments.wechat.order(orderId);
    if (state.order?.id !== orderId) return;
    await acceptOrder(order);
  } catch (error) {
    setMessage(`订单状态查询失败，将自动重试：${error.message}`, "error");
  } finally {
    state.pollInFlight = false;
    if (isPendingOrder()) schedulePoll();
  }
}

function startTracking() {
  stopTracking();
  if (!isPendingOrder()) return;
  updateCountdown();
  state.countdownTimer = window.setInterval(updateCountdown, 1000);
  schedulePoll();
}

async function createPayment() {
  if (!state.enabled || !state.selectedAmount || state.creating || isPendingOrder()) return;
  stopTracking();
  state.creating = true;
  setPaymentStatus("creating");
  setMessage("正在创建微信支付订单…");
  updateControls();

  try {
    const order = await payments.wechat.createNative(state.selectedAmount);
    await acceptOrder(order);
    startTracking();
  } catch (error) {
    showPaymentEmpty("二维码生成失败", "请检查支付配置后重试", "failed");
    setMessage(error.message, "error");
  } finally {
    state.creating = false;
    updateControls();
  }
}

async function refreshWallet() {
  el.refresh.disabled = true;
  const label = el.refresh.textContent;
  el.refresh.textContent = "刷新中";
  try {
    await loadWallet();
  } finally {
    el.refresh.disabled = false;
    el.refresh.textContent = label;
  }
}

async function main() {
  const user = await requireAuth();
  if (!user) return;
  mountNav("");
  el.username.textContent = user.email || user.username;
  el.createPayment.addEventListener("click", createPayment);
  el.customAmount.addEventListener("input", onCustomAmountInput);
  el.retryPayment.addEventListener("click", createPayment);
  el.refresh.addEventListener("click", refreshWallet);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && isPendingOrder()) schedulePoll(0);
  });
  window.addEventListener("pagehide", stopTracking);
  await Promise.all([loadWallet(), loadPaymentConfig()]);
  await recoverPendingPayment();
}

main();
