import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactPlugin from 'eslint-plugin-react';
import jsxA11y from 'eslint-plugin-jsx-a11y';

const globalIgnores = [
  '**/node_modules/**',
  '**/dist/**',
  '**/tmp/**',
  '**/.tmp/**',
  '**/.venv/**',
  '**/output/**',
  '**/*.min.js',
  '**/*.generated.*', // 生成文件不参与 lint（与 google_style_audit.mjs 的 *.generated.* 跳过对齐，防止污染尺寸/命名门禁基线）
  'third_party/**',
  '**/.playwright-mcp/**',
  '**/.worktrees/**',
  'log/**',
  'public/**',
  'public/usd/bindings/**',
  'test/**', // 大型 fixture / 回归语料（gitignored、非源码；曾含会让 ESLint 遍历崩溃的损坏条目）
  'src/features/urdf-viewer/runtime/**',
];

export default tseslint.config(
  {
    ignores: globalIgnores,
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{js,mjs,cjs,ts,tsx,jsx}'],
    plugins: {
      'react-hooks': reactHooks,
      react: reactPlugin,
      'jsx-a11y': jsxA11y,
    },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    linterOptions: {
      reportUnusedDisableDirectives: 'off',
    },
    rules: {
      // --- noise rules that intentionally stay off (legitimately hit by parsers / regex / generated code) ---
      'no-console': 'off',
      'no-cond-assign': 'off',
      'no-loss-of-precision': 'off',
      'no-regex-spaces': 'off',
      'no-undef': 'off', // TypeScript handles undefined identifiers
      'no-useless-escape': 'off',
      'no-case-declarations': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-require-imports': 'off',
      '@typescript-eslint/no-unused-expressions': 'off',

      // --- re-enabled core hygiene rules (existing backlog captured in eslint-suppressions.json) ---
      'prefer-const': 'error',
      'no-empty': ['error', { allowEmptyCatch: true }],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],

      // --- React correctness (the highest-value lint at scale) ---
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      'react/jsx-key': 'error',

      // --- accessibility (recommended set; existing backlog suppressed, burned down in Phase E) ---
      ...jsxA11y.flatConfigs.recommended.rules,
    },
  },
  {
    files: ['**/*.cjs'],
    languageOptions: {
      sourceType: 'commonjs',
      globals: {
        ...globals.node,
      },
    },
  },
);
