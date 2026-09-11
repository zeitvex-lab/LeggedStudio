#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '../..');

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(repoRoot, relativePath), 'utf8'));
}

const appPackage = readJson('package.json');
const canvasPackage = readJson('packages/react-robot-canvas/package.json');
const showJson = process.argv.includes('--json');

const versions = {
  app: {
    name: appPackage.name,
    version: appPackage.version,
  },
  package: {
    name: canvasPackage.name,
    version: canvasPackage.version,
  },
};

if (showJson) {
  console.log(JSON.stringify(versions, null, 2));
  process.exit(0);
}

console.log(`app: ${versions.app.name}@${versions.app.version}`);
console.log(`package: ${versions.package.name}@${versions.package.version}`);
