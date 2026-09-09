const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const required = [
  'VERSION',
  'package.json',
  'electron/launcher/main.js',
  'electron/launcher/index.html',
  'backend/api_complete.py',
  'backend/requirements.txt',
  'contracts/fixtures/unitree_go2.v2.json',
  'assets/robots/unitree_go2/model/robot.xml',
  'assets/robots/zex-w/model/robot.xml',
  'web/workbench.html',
  'packaging/electron-builder.embedded.js',
  'packaging/electron-builder.online.js',
  'scripts/stage_windows_runtime.ps1',
  'scripts/package_windows_embedded.ps1',
  'scripts/verify_windows_embedded.ps1',
  'scripts/provision_windows_runtime.ps1',
  'scripts/package_windows_online.ps1',
  'scripts/verify_windows_online.ps1',
];

const missing = required.filter((file) => !fs.existsSync(path.join(root, file)));
if (missing.length) {
  console.error('Release check failed. Missing files:');
  missing.forEach((file) => console.error(`- ${file}`));
  process.exit(1);
}

const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const version = fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim();
if (pkg.version !== version) {
  console.error(`Release version mismatch: package.json=${pkg.version}, VERSION=${version}`);
  process.exit(1);
}

const packageConfig = pkg.build || {};
if (!Array.isArray(packageConfig.extraResources) || !packageConfig.extraResources.length) {
  console.error('Release check failed: electron-builder extraResources are empty');
  process.exit(1);
}

// Workspace 副本完整性：运行时优先伺服 workspace/packages，config 引用的
// 包内文件必须存在（夜班同步 config 漏带 policies 导致 404 的教训）。
const workspacePackages = path.join(root, 'workspace', 'packages');
if (fs.existsSync(workspacePackages)) {
  const problems = [];
  for (const entry of fs.readdirSync(workspacePackages, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const configPath = path.join(workspacePackages, entry.name, 'simulation', 'config.json');
    if (!fs.existsSync(configPath)) continue;
    let config;
    try {
      config = JSON.parse(fs.readFileSync(configPath, 'utf8').replace(/^﻿/, ''));
    } catch {
      problems.push(`${entry.name}: simulation/config.json 不可解析`);
      continue;
    }
    for (const policy of config.policies || []) {
      const rel = policy && policy.path;
      if (rel && !path.isAbsolute(rel) && !fs.existsSync(path.join(workspacePackages, entry.name, rel))) {
        problems.push(`${entry.name}: ${rel}`);
      }
    }
  }
  if (problems.length) {
    console.error('Release check failed. Workspace package copies reference missing files:');
    problems.forEach((item) => console.error(`- ${item}`));
    process.exit(1);
  }
}

const embeddedRuntime = path.join(root, 'build', 'embedded-runtime');
if (fs.existsSync(embeddedRuntime)) {
  const manifestPath = path.join(embeddedRuntime, 'runtime-manifest.json');
  if (!fs.existsSync(manifestPath)) {
    console.error('Release check failed: embedded runtime is incomplete');
    process.exit(1);
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8').replace(/^\uFEFF/, ''));
  const pythonPath = path.join(embeddedRuntime, manifest.python || '');
  if (!manifest.python || !fs.existsSync(pythonPath)) {
    console.error(`Release check failed: embedded Python is missing: ${pythonPath}`);
    process.exit(1);
  }
}

console.log(`Release check passed for Legged Studio ${version}`);
console.log(`Required resources: ${required.length}`);
console.log('Runtime policy: control plane and training adapters are configured after launch.');
