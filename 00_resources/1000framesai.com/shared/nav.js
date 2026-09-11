// Platform-wide navigation. Each page calls mountNav('robots') etc.
// To add a new pipeline step, add an entry to STEPS; nothing else changes.
import { auth } from "./api.js";

export const STEPS = [
  { id: "robots", label: "机器人配置", href: "/robots/" },
  { id: "algorithms", label: "算法", href: "/algorithms/" },
  { id: "train", label: "训练", href: "/train/" },
  { id: "sim", label: "仿真验证", href: "/sim2sim/" },
  { id: "ops", label: "上线检查", href: "/ops/", adminOnly: true },
];

let authStatusPromise = null;

function loadAuthStatus() {
  if (!authStatusPromise) authStatusPromise = auth.me();
  return authStatusPromise;
}

function renderNavSteps(currentStepId, isAdmin = false) {
  const list = document.querySelector("#platform-nav .pnav-steps");
  if (!list) return;
  const steps = STEPS.filter((step) => !step.adminOnly || isAdmin);
  list.innerHTML = `
    <li class="pnav-step pnav-home-step ${currentStepId ? "" : "active"}">
      <a href="/">
        <span class="pnav-home-icon" aria-hidden="true">⌂</span>
        <span>首页</span>
      </a>
    </li>
  ` + steps.map(
    (step, index) => `
      <li class="pnav-step ${step.id === currentStepId ? "active" : ""}">
        <span class="pnav-arrow">›</span>
        <a href="${step.href}">
          <span class="pnav-num">${index + 1}</span>
          <span>${step.label}</span>
        </a>
      </li>`,
  ).join("");
}

export function mountNav(currentStepId) {
  const nav = document.createElement("nav");
  nav.id = "platform-nav";
  nav.innerHTML = `
    <a class="pnav-brand" href="/">
      <span class="pnav-logo">LP</span>
      <span class="pnav-title">Locomotion</span>
    </a>
    <ol class="pnav-steps"></ol>
    <span class="pnav-user" id="pnav-user"></span>
  `;
  document.body.prepend(nav);
  document.body.style.paddingTop = "56px";
  renderNavSteps(currentStepId);
  renderNavUser(currentStepId);
}

// Fetch current user and render the account widget in the nav.
async function renderNavUser(currentStepId) {
  const slot = document.getElementById("pnav-user");
  if (!slot) return;
  try {
    const data = await loadAuthStatus();
    renderNavSteps(currentStepId, data.user?.role === "admin");
    if (data.user) {
      const cents = Number(data.user.balance_cents || 0);
      const yuan = (cents / 100).toFixed(2);

      const balance = document.createElement("a");
      balance.href = "/wallet/";
      balance.className = "pnav-balance";
      balance.title = "点击充值";
      balance.textContent = `¥${yuan}`;

      const account = document.createElement("span");
      account.className = "pnav-username";
      account.title = "已登录";
      account.textContent = data.user.email || data.user.username;

      const logout = document.createElement("a");
      logout.href = "#";
      logout.className = "pnav-logout";
      logout.textContent = "退出";
      logout.addEventListener("click", async (e) => {
        e.preventDefault();
        try { await auth.logout(); } catch (_) {}
        location.href = "/login/";
      });

      slot.replaceChildren(balance);
      if (data.user.role === "admin") {
        const billing = document.createElement("a");
        billing.href = "/billing/";
        billing.className = "pnav-billing";
        billing.title = "计费管理";
        billing.textContent = "计费";
        slot.append(billing);
      }
      slot.append(account, logout);
    } else {
      const login = document.createElement("a");
      login.href = "/login/";
      login.className = "pnav-login";
      login.textContent = "登录";
      slot.replaceChildren(login);
    }
  } catch (_) {
    slot.replaceChildren();
  }
}

// Page guard: redirect to /login/ if not authenticated. Returns the user or null.
export async function requireAuth() {
  try {
    const data = await loadAuthStatus();
    if (!data.user) {
      location.href = "/login/?next=" + encodeURIComponent(location.pathname + location.search);
      return null;
    }
    return data.user;
  } catch (_) {
    location.href = "/login/";
    return null;
  }
}

// Page guard for administrator-only frontend surfaces.
export async function requireAdmin() {
  try {
    const data = await loadAuthStatus();
    if (!data.user) {
      location.href = "/login/?next=" + encodeURIComponent(location.pathname + location.search);
      return null;
    }
    if (data.user.role !== "admin") {
      location.href = "/";
      return null;
    }
    return data.user;
  } catch (_) {
    location.href = "/login/";
    return null;
  }
}
