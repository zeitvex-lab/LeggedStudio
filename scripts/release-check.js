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
  'assets/robots/unitree_go2/go2.xml',
  'assets/robots/unitree_go2w/go2w.xml',
  'web/workbench.html',
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

console.log(`Release check passed for Legged Studio ${version}`);
console.log(`Required resources: ${required.length}`);
console.log('Runtime policy: control plane and training adapters are configured after launch.');
