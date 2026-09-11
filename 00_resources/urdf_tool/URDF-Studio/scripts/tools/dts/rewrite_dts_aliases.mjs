import { promises as fs } from 'node:fs';
import path from 'node:path';

const targetDirArg = process.argv[2];

if (!targetDirArg) {
  throw new Error('Usage: node rewrite_dts_aliases.mjs <declaration-directory>');
}

const targetDir = path.resolve(process.cwd(), targetDirArg);
const aliasPrefix = '@/';

function toPosix(filePath) {
  return filePath.split(path.sep).join('/');
}

function resolveAlias(filePath, specifier) {
  if (!specifier.startsWith(aliasPrefix)) {
    return specifier;
  }

  const targetPath = path.join(targetDir, specifier.slice(aliasPrefix.length));
  let relativePath = toPosix(path.relative(path.dirname(filePath), targetPath));

  if (!relativePath.startsWith('.')) {
    relativePath = `./${relativePath}`;
  }

  return relativePath;
}

async function walk(dir, filePaths) {
  const entries = await fs.readdir(dir, { withFileTypes: true });

  await Promise.all(
    entries.map(async (entry) => {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath, filePaths);
        return;
      }

      if (entry.isFile() && entry.name.endsWith('.d.ts')) {
        filePaths.push(fullPath);
      }
    }),
  );
}

async function rewriteDeclarationFile(filePath) {
  const original = await fs.readFile(filePath, 'utf8');
  const rewritten = original
    .replace(/from\s+(['"])(@\/[^'"]+)\1/g, (_match, quote, specifier) => {
      return `from ${quote}${resolveAlias(filePath, specifier)}${quote}`;
    })
    .replace(/import\((['"])(@\/[^'"]+)\1\)/g, (_match, quote, specifier) => {
      return `import(${quote}${resolveAlias(filePath, specifier)}${quote})`;
    });

  if (rewritten !== original) {
    await fs.writeFile(filePath, rewritten, 'utf8');
  }
}

const declarationFiles = [];
await walk(targetDir, declarationFiles);
await Promise.all(declarationFiles.map(rewriteDeclarationFile));
