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
  'contracts/fixtures/unitree_go2w.v2.json',
  'assets/robots/unitree_go2/model/robot.xml',
  'assets/robots/unitree_go2w/model/robot.xml',
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
