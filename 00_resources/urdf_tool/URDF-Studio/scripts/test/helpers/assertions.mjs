#!/usr/bin/env node

/**
 * Lightweight assertion + test-suite helpers for browser/e2e regression scripts.
 *
 * Zero-dependency, framework-free. A "suite" accumulates pass/fail counts and
 * prints a one-line-per-assertion trace; `printSummary` returns a boolean that
 * callers map to `process.exitCode` (true = all passed).
 *
 * Contract consumed by scripts/test/browser/helpers/*.mjs and test_*.mjs:
 *   createTestSuite(name) -> suite
 *   assert(suite, condition, message)
 *   assertEqual(suite, actual, expected, message)
 *   assertGreaterThan(suite, value, threshold, message)
 *   assertNonNull(suite, value, message)
 *   printSummary(suite) -> boolean
 */

/**
 * @typedef {Object} TestSuite
 * @property {string} name
 * @property {Array<{ index: number, ok: boolean, message: string, detail?: string }>} results
 * @property {number} passed
 * @property {number} failed
 */

/**
 * @param {string} name
 * @returns {TestSuite}
 */
export function createTestSuite(name) {
  return { name: String(name ?? 'suite'), results: [], passed: 0, failed: 0 };
}

function record(suite, ok, message, detail) {
  const index = suite.results.length + 1;
  suite.results.push({ index, ok, message: String(message ?? ''), detail });
  if (ok) suite.passed += 1;
  else suite.failed += 1;

  const mark = ok ? '✓' : '✗';
  const suffix = detail != null && detail !== '' ? ` (${detail})` : '';
  // eslint-disable-next-line no-console
  console.log(`[suite:${suite.name}] ${mark} assert ${index}: ${message}${suffix}`);
  return ok;
}

/**
 * Record a boolean assertion.
 * @param {TestSuite} suite
 * @param {unknown} condition
 * @param {string} message
 */
export function assert(suite, condition, message) {
  return record(suite, Boolean(condition), message);
}

/**
 * Record a strict (SameValueZero via Object.is) equality assertion.
 * @param {TestSuite} suite
 */
export function assertEqual(suite, actual, expected, message) {
  const ok = Object.is(actual, expected);
  const detail = ok ? formatValue(actual) : `expected ${formatValue(expected)}, got ${formatValue(actual)}`;
  return record(suite, ok, message, detail);
}

/**
 * Record `value > threshold`.
 * @param {TestSuite} suite
 */
export function assertGreaterThan(suite, value, threshold, message) {
  const ok = typeof value === 'number' && Number.isFinite(value) && value > threshold;
  const detail = ok ? `${formatValue(value)} > ${formatValue(threshold)}` : `expected > ${formatValue(threshold)}, got ${formatValue(value)}`;
  return record(suite, ok, message, detail);
}

/**
 * Record that `value` is neither null nor undefined.
 * @param {TestSuite} suite
 */
export function assertNonNull(suite, value, message) {
  const ok = value != null;
  return record(suite, ok, message, ok ? formatValue(value) : 'null/undefined');
}

function formatValue(value) {
  if (typeof value === 'string') return value.length > 60 ? `${value.slice(0, 57)}…` : value;
  if (typeof value === 'number' || typeof value === 'boolean' || value == null) return String(value);
  try {
    const json = JSON.stringify(value);
    return json && json.length > 60 ? `${json.slice(0, 57)}…` : json ?? String(value);
  } catch {
    return String(value);
  }
}

/**
 * Print a `[summary]` line and return whether the suite fully passed.
 * @param {TestSuite} suite
 * @returns {boolean} true when no assertion failed
 */
export function printSummary(suite) {
  const ok = suite.failed === 0;
  if (!ok) {
    for (const r of suite.results) {
      if (!r.ok) console.log(`[suite:${suite.name}]   FAILED #${r.index}: ${r.message}${r.detail ? ` (${r.detail})` : ''}`);
    }
  }
  // eslint-disable-next-line no-console
  console.log(`[summary:${suite.name}] passed: ${suite.passed}, failed: ${suite.failed}, exit: ${ok ? 0 : 1}`);
  return ok;
}
