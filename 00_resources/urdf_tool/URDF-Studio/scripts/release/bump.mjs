#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '../..');
const appPackagePath = path.join(repoRoot, 'package.json');
const packageLockPath = path.join(repoRoot, 'package-lock.json');
const canvasPackagePath = path.join(repoRoot, 'packages/react-robot-canvas/package.json');

const exactVersionPattern = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z-.]+)?(?:\+[0-9A-Za-z-.]+)?$/;
const releasePattern = /^(major|minor|patch)$/;

function fail(message) {
  console.error(message);
  process.exit(1);
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function parseArgs(argv) {
  const parsed = { app: undefined, package: undefined };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--app') {
      parsed.app = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === '--package') {
      parsed.package = argv[index + 1];
      index += 1;
      continue;
    }
  }

  return parsed;
}

function resolveNextVersion(currentVersion, requestedRelease) {
  if (!requestedRelease) return currentVersion;
  if (exactVersionPattern.test(requestedRelease)) return requestedRelease;
  if (!releasePattern.test(requestedRelease)) {
    fail(
      `Unsupported version spec "${requestedRelease}". Use major|minor|patch or an exact semver.`,
    );
  }

  const [major, minor, patch] = currentVersion
    .split('.')
    .map((segment) => Number.parseInt(segment, 10));
  if ([major, minor, patch].some((segment) => Number.isNaN(segment))) {
    fail(`Current version "${currentVersion}" is not a plain semver.`);
  }

  switch (requestedRelease) {
    case 'major':
      return `${major + 1}.0.0`;
    case 'minor':
      return `${major}.${minor + 1}.0`;
    case 'patch':
      return `${major}.${minor}.${patch + 1}`;
    default:
      fail(`Unsupported release type "${requestedRelease}".`);
  }
}

function replaceOrFail(content, pattern, replacement, failureMessage) {
  const matcher = new RegExp(pattern.source, pattern.flags);
  if (!matcher.test(content)) {
    fail(failureMessage);
  }
  const nextContent = content.replace(pattern, replacement);
  return nextContent;
}

function updatePackageLock(appVersion) {
  let content = fs.readFileSync(packageLockPath, 'utf8');
  content = replaceOrFail(
    content,
    /("version": ")([^"]+)(")/,
    (_, prefix, __, suffix) => `${prefix}${appVersion}${suffix}`,
    'Failed to update root package-lock version.',
  );
  content = replaceOrFail(
    content,
    /("packages": \{\n    "": \{\n      "name": "[^"]+",\n      "version": ")([^"]+)(")/,
    (_, prefix, __, suffix) => `${prefix}${appVersion}${suffix}`,
    'Failed to update root package-lock workspace version.',
  );
  fs.writeFileSync(packageLockPath, content);
}

function updateReadmeVersions(appVersion, packageVersion) {
  const replacements = [
    {
      filePath: path.join(repoRoot, 'README.md'),
      patterns: [
        {
          pattern: /^(- root app: `urdf-studio@)([^`]+)(`.*)$/m,
          replacement: (_, prefix, __, suffix) => `${prefix}${appVersion}${suffix}`,
        },
        {
          pattern: /^(- published package: `@urdf-studio\/react-robot-canvas@)([^`]+)(`.*)$/m,
          replacement: (_, prefix, __, suffix) => `${prefix}${packageVersion}${suffix}`,
        },
      ],
    },
    {
      filePath: path.join(repoRoot, 'docs/README_CN.md'),
      patterns: [
        {
          pattern: /^(- 根应用：`urdf-studio@)([^`]+)(`.*)$/m,
          replacement: (_, prefix, __, suffix) => `${prefix}${appVersion}${suffix}`,
        },
        {
          pattern: /^(- 对外发布包：`@urdf-studio\/react-robot-canvas@)([^`]+)(`.*)$/m,
          replacement: (_, prefix, __, suffix) => `${prefix}${packageVersion}${suffix}`,
        },
      ],
    },
  ];

  replacements.forEach(({ filePath, patterns }) => {
    let content = fs.readFileSync(filePath, 'utf8');
    patterns.forEach(({ pattern, replacement }) => {
      content = replaceOrFail(
        content,
        pattern,
        replacement,
        `Failed to update version references in ${path.relative(repoRoot, filePath)}.`,
      );
    });
    fs.writeFileSync(filePath, content);
  });
}

const requested = parseArgs(process.argv.slice(2));
if (!requested.app && !requested.package) {
  fail(
    'Nothing to bump. Use --app <major|minor|patch|x.y.z> and/or --package <major|minor|patch|x.y.z>.',
  );
}

const appPackage = readJson(appPackagePath);
const canvasPackage = readJson(canvasPackagePath);

const nextAppVersion = resolveNextVersion(appPackage.version, requested.app);
const nextPackageVersion = resolveNextVersion(canvasPackage.version, requested.package);

if (requested.app) {
  appPackage.version = nextAppVersion;
  writeJson(appPackagePath, appPackage);
  updatePackageLock(nextAppVersion);
}

if (requested.package) {
  canvasPackage.version = nextPackageVersion;
  writeJson(canvasPackagePath, canvasPackage);
}

updateReadmeVersions(
  requested.app ? nextAppVersion : appPackage.version,
  requested.package ? nextPackageVersion : canvasPackage.version,
);

console.log(`app: ${appPackage.name}@${requested.app ? nextAppVersion : appPackage.version}`);
console.log(
  `package: ${canvasPackage.name}@${requested.package ? nextPackageVersion : canvasPackage.version}`,
);
