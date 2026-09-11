import type { RobotFile } from '@/types';

const USD_BINARY_MAGIC = new Uint8Array([80, 88, 82, 45, 85, 83, 68, 67]); // "PXR-USDC"
const usdTextDecoder = new TextDecoder();
export const MAX_EAGER_TEXT_USD_BYTES = 1024 * 1024;

function hasBinaryMagic(bytes: Uint8Array, magic: Uint8Array): boolean {
  if (bytes.length < magic.length) return false;

  for (let index = 0; index < magic.length; index += 1) {
    if (bytes[index] !== magic[index]) return false;
  }

  return true;
}

function isLikelyTextBuffer(bytes: Uint8Array): boolean {
  const sample = bytes.subarray(0, Math.min(bytes.length, 512));
  if (sample.some((byte) => byte === 0)) return false;

  const decoded = usdTextDecoder.decode(sample);
  if (decoded.trimStart().startsWith('#usda')) return true;

  let printableCount = 0;
  for (const byte of sample) {
    if (byte === 9 || byte === 10 || byte === 13 || (byte >= 32 && byte <= 126)) {
      printableCount += 1;
    }
  }

  return sample.length > 0 && printableCount / sample.length > 0.9;
}

export function isUsdFamilyPath(path: string): boolean {
  const lowerPath = path.toLowerCase();
  return (
    lowerPath.endsWith('.usd') ||
    lowerPath.endsWith('.usda') ||
    lowerPath.endsWith('.usdc') ||
    lowerPath.endsWith('.usdz')
  );
}

export function createImportedUsdFile(name: string, bytes: Uint8Array): RobotFile {
  const lowerName = name.toLowerCase();
  const isBinaryUsd =
    lowerName.endsWith('.usdc') ||
    lowerName.endsWith('.usdz') ||
    hasBinaryMagic(bytes, USD_BINARY_MAGIC);
  const isTextUsd = !isBinaryUsd && (lowerName.endsWith('.usda') || isLikelyTextBuffer(bytes));
  const shouldDecodeTextContent = isTextUsd && bytes.byteLength <= MAX_EAGER_TEXT_USD_BYTES;

  return {
    name,
    content: shouldDecodeTextContent ? usdTextDecoder.decode(bytes) : '',
    format: 'usd',
  };
}

export async function createImportedUsdFileFromLooseFile(
  name: string,
  file: File,
): Promise<RobotFile> {
  const lowerName = name.toLowerCase();

  if (lowerName.endsWith('.usdc') || lowerName.endsWith('.usdz')) {
    return {
      name,
      content: '',
      format: 'usd',
    };
  }

  if (lowerName.endsWith('.usda')) {
    return {
      name,
      content: file.size <= MAX_EAGER_TEXT_USD_BYTES ? await file.text() : '',
      format: 'usd',
    };
  }

  const sampleBytes = new Uint8Array(await file.slice(0, Math.min(file.size, 2048)).arrayBuffer());
  const isBinaryUsd = hasBinaryMagic(sampleBytes, USD_BINARY_MAGIC);
  const isTextUsd = !isBinaryUsd && isLikelyTextBuffer(sampleBytes);

  return {
    name,
    content: isTextUsd && file.size <= MAX_EAGER_TEXT_USD_BYTES ? await file.text() : '',
    format: 'usd',
  };
}
