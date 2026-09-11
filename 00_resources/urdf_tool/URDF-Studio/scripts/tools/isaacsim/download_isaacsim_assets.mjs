#!/usr/bin/env node

import fs from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import process from 'node:process';
import { pipeline } from 'node:stream/promises';
import { URL } from 'node:url';

const BUCKET_URL = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/';
const DEFAULT_DEST_DIR = path.resolve('tmp/isaacsim-assets');
const DEFAULT_MANIFEST_PATH = path.resolve('tmp/isaacsim-assets/manifest.json');
const DEFAULT_VERSION = '5.0';
const DEFAULT_CONCURRENCY = 6;

const PRESETS = {
  unitree: [
    'Isaac/Robots/Unitree/',
    'Isaac/IsaacLab/Robots/Unitree/',
  ],
  'isaac-unitree': ['Isaac/Robots/Unitree/'],
  'isaaclab-unitree': ['Isaac/IsaacLab/Robots/Unitree/'],
  'isaac-robots': ['Isaac/Robots/'],
  'isaaclab-robots': ['Isaac/IsaacLab/Robots/'],
};

function printUsage() {
  console.log(`Usage:
  node scripts/tools/isaacsim/download_isaacsim_assets.mjs [options]

Options:
  --preset <name>       Prefix preset. Available: ${Object.keys(PRESETS).join(', ')}
  --prefix <prefix>     S3 prefix to list/download. May be full "Assets/Isaac/5.0/..."
                        or relative to "Assets/Isaac/<version>/". Repeatable.
  --version <version>   Isaac Sim asset version. Default: ${DEFAULT_VERSION}
  --dest <dir>          Download destination. Default: ${DEFAULT_DEST_DIR}
  --manifest <path>     Manifest output JSON. Default: ${DEFAULT_MANIFEST_PATH}
  --download            Download objects. Without this flag the tool only lists and writes manifest.
  --usd-only            Only include .usd/.usda/.usdc files. Not recommended for complete models.
  --force               Re-download files even when local size matches.
  --concurrency <n>     Download concurrency. Default: ${DEFAULT_CONCURRENCY}
  --help                Show this help.

Examples:
  # List IsaacLab Unitree assets and write manifest only.
  node scripts/tools/isaacsim/download_isaacsim_assets.mjs --preset isaaclab-unitree

  # Download both Isaac Sim and IsaacLab Unitree robot directories.
  node scripts/tools/isaacsim/download_isaacsim_assets.mjs --preset unitree --download

  # Download one model directory.
  node scripts/tools/isaacsim/download_isaacsim_assets.mjs \\
    --prefix Isaac/IsaacLab/Robots/Unitree/Go2/ --download
`);
}

function parseArgs(argv) {
  const options = {
    concurrency: DEFAULT_CONCURRENCY,
    destDir: DEFAULT_DEST_DIR,
    download: false,
    force: false,
    help: false,
    manifestPath: DEFAULT_MANIFEST_PATH,
    prefixes: [],
    usdOnly: false,
    version: DEFAULT_VERSION,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) {
        throw new Error(`Missing value for ${arg}`);
      }
      return argv[index];
    };

    switch (arg) {
      case '--preset': {
        const preset = next();
        const presetPrefixes = PRESETS[preset];
        if (!presetPrefixes) {
          throw new Error(`Unknown preset "${preset}". Available: ${Object.keys(PRESETS).join(', ')}`);
        }
        options.prefixes.push(...presetPrefixes);
        break;
      }
      case '--prefix':
        options.prefixes.push(next());
        break;
      case '--version':
        options.version = next();
        break;
      case '--dest':
        options.destDir = path.resolve(next());
        break;
      case '--manifest':
        options.manifestPath = path.resolve(next());
        break;
      case '--download':
        options.download = true;
        break;
      case '--usd-only':
        options.usdOnly = true;
        break;
      case '--force':
        options.force = true;
        break;
      case '--concurrency':
        options.concurrency = Number.parseInt(next(), 10);
        break;
      case '--help':
      case '-h':
        options.help = true;
        break;
      default:
        throw new Error(`Unknown option: ${arg}`);
    }
  }

  if (!Number.isInteger(options.concurrency) || options.concurrency < 1) {
    throw new Error(`Invalid --concurrency: ${options.concurrency}`);
  }

  return options;
}

function normalizePrefix(prefix, version) {
  const normalized = prefix.replace(/^\/+/, '');
  if (normalized.startsWith('Assets/')) {
    return normalized.endsWith('/') ? normalized : `${normalized}/`;
  }
  return `Assets/Isaac/${version}/${normalized.endsWith('/') ? normalized : `${normalized}/`}`;
}

function decodeXml(value) {
  return value
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'");
}

function formatBytes(bytes) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const fractionDigits = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(fractionDigits)} ${units[unitIndex]}`;
}

function s3UrlForKey(key) {
  return `${BUCKET_URL}${key.split('/').map(encodeURIComponent).join('/')}`;
}

function request(url) {
  return new Promise((resolve, reject) => {
    https
      .get(url, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          response.resume();
          resolve(request(response.headers.location));
          return;
        }
        resolve(response);
      })
      .on('error', reject);
  });
}

async function fetchText(url) {
  const response = await request(url);
  if (response.statusCode !== 200) {
    response.resume();
    throw new Error(`GET ${url} returned ${response.statusCode}`);
  }

  response.setEncoding('utf8');
  let data = '';
  for await (const chunk of response) {
    data += chunk;
  }
  return data;
}

async function listObjects(prefix) {
  const contents = [];
  let continuationToken = '';

  do {
    const url = new URL(BUCKET_URL);
    url.searchParams.set('list-type', '2');
    url.searchParams.set('prefix', prefix);
    if (continuationToken) {
      url.searchParams.set('continuation-token', continuationToken);
    }

    const xml = await fetchText(url.toString());
    for (const match of xml.matchAll(
      /<Contents>.*?<Key>(.*?)<\/Key>.*?<LastModified>(.*?)<\/LastModified>.*?<ETag>(.*?)<\/ETag>.*?<Size>(\d+)<\/Size>.*?<\/Contents>/gs,
    )) {
      contents.push({
        key: decodeXml(match[1]),
        lastModified: match[2],
        etag: decodeXml(match[3]),
        size: Number(match[4]),
      });
    }

    const tokenMatch = xml.match(/<NextContinuationToken>(.*?)<\/NextContinuationToken>/);
    continuationToken = tokenMatch ? decodeXml(tokenMatch[1]) : '';
  } while (continuationToken);

  return contents;
}

function uniqueObjects(objects) {
  const byKey = new Map();
  for (const object of objects) {
    byKey.set(object.key, object);
  }
  return [...byKey.values()].sort((left, right) => left.key.localeCompare(right.key));
}

async function localFileMatches(localPath, size) {
  try {
    const stats = await fs.stat(localPath);
    return stats.isFile() && stats.size === size;
  } catch {
    return false;
  }
}

async function downloadObject(object, options) {
  const localPath = path.join(options.destDir, object.key);
  if (!options.force && await localFileMatches(localPath, object.size)) {
    return { key: object.key, localPath, status: 'skipped' };
  }

  await fs.mkdir(path.dirname(localPath), { recursive: true });
  const tempPath = `${localPath}.part`;
  const response = await request(s3UrlForKey(object.key));
  if (response.statusCode !== 200) {
    response.resume();
    throw new Error(`GET ${s3UrlForKey(object.key)} returned ${response.statusCode}`);
  }

  await pipeline(response, createWriteStream(tempPath));
  const stats = await fs.stat(tempPath);
  if (stats.size !== object.size) {
    throw new Error(`Downloaded size mismatch for ${object.key}: got ${stats.size}, expected ${object.size}`);
  }
  await fs.rename(tempPath, localPath);
  return { key: object.key, localPath, status: 'downloaded' };
}

async function runPool(items, concurrency, worker) {
  const results = [];
  let nextIndex = 0;

  async function runWorker() {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await worker(items[index], index);
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => runWorker()));
  return results;
}

function summarize(prefixes, objects) {
  const totalBytes = objects.reduce((total, object) => total + object.size, 0);
  const usdObjects = objects.filter((object) => /\.usd[ac]?$/i.test(object.key));
  return {
    prefixes,
    objectCount: objects.length,
    totalBytes,
    totalSize: formatBytes(totalBytes),
    usdObjectCount: usdObjects.length,
    largestUsdObjects: usdObjects
      .slice()
      .sort((left, right) => right.size - left.size)
      .slice(0, 25)
      .map((object) => ({
        key: object.key,
        size: object.size,
        sizeLabel: formatBytes(object.size),
      })),
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printUsage();
    return;
  }
  if (options.prefixes.length === 0) {
    throw new Error('Provide at least one --prefix or --preset. Use --help for examples.');
  }

  const prefixes = [...new Set(options.prefixes.map((prefix) => normalizePrefix(prefix, options.version)))];
  const listedObjects = [];
  for (const prefix of prefixes) {
    console.error(`Listing ${prefix}`);
    listedObjects.push(...await listObjects(prefix));
  }

  const objects = uniqueObjects(listedObjects).filter(
    (object) => !options.usdOnly || /\.usd[ac]?$/i.test(object.key),
  );
  const manifest = {
    generatedAtUtc: new Date().toISOString(),
    bucketUrl: BUCKET_URL,
    download: options.download,
    destDir: options.destDir,
    usdOnly: options.usdOnly,
    summary: summarize(prefixes, objects),
    objects,
  };

  await fs.mkdir(path.dirname(options.manifestPath), { recursive: true });
  await fs.writeFile(options.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

  if (options.download) {
    let completed = 0;
    const results = await runPool(objects, options.concurrency, async (object) => {
      const result = await downloadObject(object, options);
      completed += 1;
      if (completed % 25 === 0 || completed === objects.length) {
        console.error(`Downloaded/listed ${completed}/${objects.length}`);
      }
      return result;
    });
    manifest.downloadResults = results;
    manifest.downloadSummary = results.reduce(
      (summary, result) => {
        summary[result.status] = (summary[result.status] || 0) + 1;
        return summary;
      },
      {},
    );
    await fs.writeFile(options.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  }

  console.log(JSON.stringify(manifest.summary, null, 2));
  console.log(`Manifest: ${options.manifestPath}`);
  if (options.download) {
    console.log(`Downloaded to: ${options.destDir}`);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
