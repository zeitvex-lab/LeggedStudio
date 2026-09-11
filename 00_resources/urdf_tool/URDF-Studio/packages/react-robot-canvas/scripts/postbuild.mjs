import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const packageDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(packageDir, '../..');
const distDir = path.join(packageDir, 'dist');
const declarationsDir = path.join(distDir, 'types');
const fontsSourceDir = path.join(repoRoot, 'public', 'fonts');
const fontsTargetDir = path.join(distDir, 'fonts');
const stableCssPath = path.join(distDir, 'style.css');

async function ensureSingleCssFile() {
  const cssFiles = [];

  async function walk(dir) {
    const entries = await fs.readdir(dir, { withFileTypes: true });

    await Promise.all(
      entries.map(async (entry) => {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          await walk(fullPath);
          return;
        }

        if (entry.name.endsWith('.css')) {
          cssFiles.push(fullPath);
        }
      })
    );
  }

  await walk(distDir);

  if (cssFiles.length !== 1) {
    throw new Error(`Expected exactly one CSS asset in ${distDir}, found: ${cssFiles.join(', ') || '(none)'}`);
  }

  return cssFiles[0];
}

async function rewriteCss(cssPath) {
  const css = await fs.readFile(cssPath, 'utf8');
  const rewrittenCss = css.replaceAll('/fonts/', './fonts/');

  await fs.writeFile(stableCssPath, rewrittenCss, 'utf8');

  if (cssPath !== stableCssPath) {
    await fs.unlink(cssPath);
  }
}

async function copyFonts() {
  await fs.mkdir(fontsTargetDir, { recursive: true });
  const fontFiles = await fs.readdir(fontsSourceDir);

  await Promise.all(
    fontFiles.map((file) =>
      fs.copyFile(path.join(fontsSourceDir, file), path.join(fontsTargetDir, file))
    )
  );
}

async function pruneUnusedDeclarations() {
  await fs.rm(path.join(declarationsDir, 'store'), { recursive: true, force: true });
}

const cssPath = await ensureSingleCssFile();
await rewriteCss(cssPath);
await copyFonts();
await pruneUnusedDeclarations();
