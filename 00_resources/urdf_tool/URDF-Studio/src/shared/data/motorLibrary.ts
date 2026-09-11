/**
 * Motor library helpers.
 * The default catalog lives in JSON so specs are maintained as data, not TS code.
 */
import type { MotorSpec } from '@/types';

import defaultMotorLibraryData from './defaultMotorLibrary.json';

export type MotorLibrary = Record<string, MotorSpec[]>;

const MOTOR_LIBRARY_CATALOG_FILE_NAMES = new Set(['motor-library.json', 'motor_library.json']);

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const normalizeOptionalString = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;

export function cloneMotorLibrary(library: MotorLibrary): MotorLibrary {
  return Object.fromEntries(
    Object.entries(library).map(([brand, motors]) => [
      brand,
      motors.map((motor) => ({ ...motor })),
    ]),
  );
}

export function parseMotorSpec(input: unknown, context: string): MotorSpec {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error(`[motorLibrary] Invalid motor spec at ${context}.`);
  }

  const candidate = input as Partial<MotorSpec>;
  const name = typeof candidate.name === 'string' ? candidate.name.trim() : '';
  if (!name) {
    throw new Error(`[motorLibrary] Missing motor name at ${context}.`);
  }

  if (!isFiniteNumber(candidate.armature)) {
    throw new Error(`[motorLibrary] Invalid armature for "${name}" at ${context}.`);
  }

  if (!isFiniteNumber(candidate.velocity)) {
    throw new Error(`[motorLibrary] Invalid velocity for "${name}" at ${context}.`);
  }

  if (!isFiniteNumber(candidate.effort)) {
    throw new Error(`[motorLibrary] Invalid effort for "${name}" at ${context}.`);
  }

  return {
    name,
    armature: candidate.armature,
    velocity: candidate.velocity,
    effort: candidate.effort,
    url: normalizeOptionalString(candidate.url),
    description: normalizeOptionalString(candidate.description),
  };
}

export function parseMotorLibraryCatalog(input: unknown, context: string): MotorLibrary {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error(`[motorLibrary] Invalid motor library payload from ${context}.`);
  }

  const parsedLibrary: MotorLibrary = {};

  for (const [brand, motors] of Object.entries(input)) {
    if (!Array.isArray(motors)) {
      throw new Error(`[motorLibrary] Brand "${brand}" from ${context} is not a motor array.`);
    }

    parsedLibrary[brand] = motors.map((motor, index) =>
      parseMotorSpec(motor, `${context}:${brand}[${index}]`),
    );
  }

  return parsedLibrary;
}

export function appendUniqueMotorSpec(target: MotorSpec[], incoming: MotorSpec): void {
  if (!incoming.name || target.some((motor) => motor.name === incoming.name)) {
    return;
  }

  target.push({ ...incoming });
}

export function mergeMotorLibraries(
  baseLibrary: MotorLibrary,
  incomingLibrary: MotorLibrary,
): MotorLibrary {
  const mergedLibrary = cloneMotorLibrary(baseLibrary);

  Object.entries(incomingLibrary).forEach(([brand, motors]) => {
    if (!mergedLibrary[brand]) {
      mergedLibrary[brand] = [];
    }

    motors.forEach((motor) => {
      appendUniqueMotorSpec(mergedLibrary[brand], motor);
    });
  });

  return mergedLibrary;
}

export function isMotorLibraryCatalogFilePath(path: string): boolean {
  const normalizedPath = path.replace(/\\/g, '/').toLowerCase();
  const fileName = normalizedPath.split('/').pop() ?? normalizedPath;
  return MOTOR_LIBRARY_CATALOG_FILE_NAMES.has(fileName);
}

export function isMotorLibraryDataFilePath(path: string): boolean {
  const normalizedPath = path.replace(/\\/g, '/').toLowerCase();

  if (isMotorLibraryCatalogFilePath(normalizedPath)) {
    return true;
  }

  return (
    normalizedPath.includes('motor library') &&
    (normalizedPath.endsWith('.txt') || normalizedPath.endsWith('.json'))
  );
}

const defaultMotorLibraryCatalog = parseMotorLibraryCatalog(
  defaultMotorLibraryData,
  'defaultMotorLibrary.json',
);

export const DEFAULT_MOTOR_LIBRARY: MotorLibrary = cloneMotorLibrary(defaultMotorLibraryCatalog);

export function normalizeMotorLibrary(
  library: MotorLibrary | null | undefined,
  context: string = 'unknown',
): MotorLibrary {
  const normalized = cloneMotorLibrary(DEFAULT_MOTOR_LIBRARY);

  if (!library || typeof library !== 'object' || Array.isArray(library)) {
    throw new Error(`[motorLibrary] Invalid library payload from ${context}.`);
  }

  if (Object.keys(library).length === 0) {
    throw new Error(`[motorLibrary] Empty library payload from ${context}.`);
  }

  Object.entries(library).forEach(([brand, motors]) => {
    if (!Array.isArray(motors)) {
      console.warn(
        `[motorLibrary] Brand "${brand}" from ${context} is not a motor array; skipping.`,
      );
      return;
    }

    if (!normalized[brand]) {
      normalized[brand] = [];
    }

    motors.forEach((motor, index) => {
      try {
        appendUniqueMotorSpec(
          normalized[brand],
          parseMotorSpec(motor, `${context}:${brand}[${index}]`),
        );
      } catch (error) {
        console.warn(
          error instanceof Error
            ? error.message
            : `[motorLibrary] Invalid motor spec at ${context}:${brand}[${index}]; skipping.`,
        );
      }
    });
  });

  return normalized;
}
