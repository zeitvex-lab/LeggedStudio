// Email registration and legacy username/email login.
import { auth, ApiError } from "../shared/api.js";

const DEFAULT_RESEND_COOLDOWN_SECONDS = 60;

let mode = "login";
let registrationOpen = true;
let pendingEmail = "";
let resendTimer = null;

const el = {
  tabs: document.getElementById("auth-tabs"),
  tabLogin: document.getElementById("tab-login"),
  tabRegister: document.getElementById("tab-register"),
  form: document.getElementById("auth-form"),
  identifierLabel: document.getElementById("identifier-label"),
  identifier: document.getElementById("identifier"),
  password: document.getElementById("password"),
  confirmField: document.getElementById("confirm-field"),
  confirmPassword: document.getElementById("confirm-password"),
  error: document.getElementById("error"),
  submit: document.getElementById("submit"),
  regNote: document.getElementById("reg-note"),
  sentState: document.getElementById("sent-state"),
  sentEmail: document.getElementById("sent-email"),
  resend: document.getElementById("resend"),
  resendStatus: document.getElementById("resend-status"),
  backToLogin: document.getElementById("back-to-login"),
  verifyState: document.getElementById("verify-state"),
  verifyTitle: document.getElementById("verify-title"),
  verifyStatus: document.getElementById("verify-status"),
  verifyLogin: document.getElementById("verify-login"),
};

function nextUrl() {
  const value = new URLSearchParams(location.search).get("next");
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/";
  try {
    const target = new URL(value, location.origin);
    if (target.origin !== location.origin) return "/";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch (_) {
    return "/";
  }
}

function verificationToken() {
  if (!location.hash.startsWith("#")) return "";
  return new URLSearchParams(location.hash.slice(1)).get("verify")?.trim() || "";
}

function showPanel(panel) {
  const showForm = panel === "form";
  el.tabs.classList.toggle("hidden", !showForm);
  el.form.classList.toggle("hidden", !showForm);
  el.sentState.classList.toggle("hidden", panel !== "sent");
  el.verifyState.classList.toggle("hidden", panel !== "verify");
  if (!showForm) el.regNote.classList.add("hidden");
}

function setMode(next) {
  mode = next;
  showPanel("form");

  const isLogin = mode === "login";
  el.tabLogin.classList.toggle("active", isLogin);
  el.tabRegister.classList.toggle("active", !isLogin);
  el.tabLogin.setAttribute("aria-selected", String(isLogin));
  el.tabRegister.setAttribute("aria-selected", String(!isLogin));

  el.identifierLabel.textContent = isLogin ? "邮箱或用户名" : "邮箱";
  el.identifier.type = isLogin ? "text" : "email";
  el.identifier.autocomplete = isLogin ? "username" : "email";
  el.identifier.inputMode = isLogin ? "text" : "email";
  el.identifier.placeholder = isLogin ? "邮箱或用户名" : "name@example.com";
  el.password.autocomplete = isLogin ? "current-password" : "new-password";
  el.confirmField.classList.toggle("hidden", isLogin);
  el.confirmPassword.disabled = isLogin;
  el.confirmPassword.required = !isLogin;
  el.submit.textContent = isLogin ? "登录" : "创建账号";
  el.error.textContent = "";

  const registrationDisabled = !isLogin && !registrationOpen;
  el.regNote.classList.toggle("hidden", !registrationDisabled);
  el.submit.disabled = registrationDisabled;
}

function cooldownFrom(response) {
  const value = Number(
    response?.resend_after_seconds
      ?? response?.retry_after_seconds
      ?? response?.resend_cooldown_seconds
      ?? DEFAULT_RESEND_COOLDOWN_SECONDS,
  );
  return Number.isFinite(value) && value > 0 ? Math.ceil(value) : DEFAULT_RESEND_COOLDOWN_SECONDS;
}

function startResendCooldown(seconds = DEFAULT_RESEND_COOLDOWN_SECONDS) {
  if (resendTimer) clearInterval(resendTimer);
  let remaining = seconds;

  const render = () => {
    el.resend.disabled = remaining > 0;
    el.resend.textContent = remaining > 0 ? `重新发送 (${remaining}s)` : "重新发送";
  };

  render();
  resendTimer = setInterval(() => {
    remaining -= 1;
    render();
    if (remaining <= 0) {
      clearInterval(resendTimer);
      resendTimer = null;
    }
  }, 1000);
}

function showSent(email, response) {
  pendingEmail = email;
  el.sentEmail.textContent = email;
  el.resendStatus.textContent = "邮件可能需要几分钟到达。";
  showPanel("sent");
  startResendCooldown(cooldownFrom(response));
}

function errorMessage(error) {
  return error instanceof ApiError ? error.message : "网络错误，请重试";
}

async function verifyEmail(token) {
  showPanel("verify");
  el.verifyTitle.textContent = "正在验证邮箱";
  el.verifyStatus.textContent = "请稍候。";
  el.verifyLogin.classList.add("hidden");

  // Remove the one-time token before any further navigation or same-origin request.
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  try {
    await auth.verifyEmail(token);
    el.verifyTitle.textContent = "邮箱验证成功";
    el.verifyStatus.textContent = "正在进入平台。";
    location.replace(nextUrl());
  } catch (error) {
    el.verifyTitle.textContent = "验证链接不可用";
    el.verifyStatus.textContent = errorMessage(error);
    el.verifyLogin.classList.remove("hidden");
  }
}

el.tabLogin.addEventListener("click", () => setMode("login"));
el.tabRegister.addEventListener("click", () => setMode("register"));

el.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  el.error.textContent = "";
  el.submit.disabled = true;

  const identifier = el.identifier.value.trim();
  const password = el.password.value;
  try {
    if (mode === "login") {
      await auth.login(identifier, password);
      location.replace(nextUrl());
      return;
    }

    if (password !== el.confirmPassword.value) {
      el.error.textContent = "两次输入的密码不一致";
      return;
    }

    const email = identifier.toLowerCase();
    const response = await auth.register(email, password);
    showSent(email, response);
  } catch (error) {
    el.error.textContent = errorMessage(error);
  } finally {
    if (!el.form.classList.contains("hidden")) {
      el.submit.disabled = mode === "register" && !registrationOpen;
    }
  }
});

el.resend.addEventListener("click", async () => {
  if (!pendingEmail) return;
  el.resend.disabled = true;
  el.resendStatus.textContent = "正在重新发送。";
  try {
    const response = await auth.resendVerification(pendingEmail);
    el.resendStatus.textContent = "新的验证邮件已发送。";
    startResendCooldown(cooldownFrom(response));
  } catch (error) {
    el.resendStatus.textContent = errorMessage(error);
    el.resend.disabled = false;
  }
});

el.backToLogin.addEventListener("click", () => {
  el.identifier.value = pendingEmail;
  el.password.value = "";
  el.confirmPassword.value = "";
  setMode("login");
});

el.verifyLogin.addEventListener("click", () => setMode("login"));

(async () => {
  let authState = null;
  try {
    authState = await auth.me();
    registrationOpen = authState.registration_open !== false;
  } catch (_) { /* Keep the form available so the user can retry. */ }

  const token = verificationToken();
  if (token) {
    await verifyEmail(token);
    return;
  }
  if (authState?.user) {
    location.replace(nextUrl());
    return;
  }
  setMode("login");
})();
