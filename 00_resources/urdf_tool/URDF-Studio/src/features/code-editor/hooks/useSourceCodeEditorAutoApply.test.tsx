import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { useSourceCodeEditorAutoApply } from './useSourceCodeEditorAutoApply';

interface HookHarnessProps {
  enabled?: boolean;
  currentCode: string;
  isDirty: boolean;
  isReadOnly: boolean;
  supportsValidation: boolean;
  validationErrorCount: number;
  isValidationPending: boolean;
  isApplying: boolean;
  autoApplyBlockedCode?: string | null;
  resolveDebounceMs?: (codeLength: number) => number;
  onAutoApply: () => void;
}

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  });
  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

function createComponentRoot() {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  return { dom, root };
}

function HookHarness(props: HookHarnessProps) {
  useSourceCodeEditorAutoApply(props);
  return null;
}

async function wait(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test('useSourceCodeEditorAutoApply waits for validation to settle before auto-applying', async () => {
  const { dom, root } = createComponentRoot();
  const appliedCodes: string[] = [];
  const resolveDebounceMs = () => 20;
  let props: HookHarnessProps = {
    currentCode: '<robot name="demo" />',
    isDirty: true,
    isReadOnly: false,
    supportsValidation: true,
    validationErrorCount: 0,
    isValidationPending: true,
    isApplying: false,
    autoApplyBlockedCode: null,
    resolveDebounceMs,
    onAutoApply: () => appliedCodes.push(props.currentCode),
  };

  try {
    await act(async () => {
      root.render(React.createElement(HookHarness, props));
    });

    await act(async () => {
      await wait(40);
    });

    assert.deepEqual(appliedCodes, [], 'should not auto-apply while validation is still pending');

    props = {
      ...props,
      isValidationPending: false,
    };

    await act(async () => {
      root.render(React.createElement(HookHarness, props));
    });

    await act(async () => {
      await wait(40);
    });

    assert.deepEqual(appliedCodes, ['<robot name="demo" />']);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('useSourceCodeEditorAutoApply cancels stale timers and only auto-applies the latest code', async () => {
  const { dom, root } = createComponentRoot();
  const appliedCodes: string[] = [];
  const resolveDebounceMs = () => 30;
  let props: HookHarnessProps = {
    currentCode: '<robot name="first" />',
    isDirty: true,
    isReadOnly: false,
    supportsValidation: true,
    validationErrorCount: 0,
    isValidationPending: false,
    isApplying: false,
    autoApplyBlockedCode: null,
    resolveDebounceMs,
    onAutoApply: () => appliedCodes.push(props.currentCode),
  };

  try {
    await act(async () => {
      root.render(React.createElement(HookHarness, props));
    });

    await act(async () => {
      await wait(10);
    });

    props = {
      ...props,
      currentCode: '<robot name="second" />',
    };

    await act(async () => {
      root.render(React.createElement(HookHarness, props));
    });

    await act(async () => {
      await wait(50);
    });

    assert.deepEqual(appliedCodes, ['<robot name="second" />']);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('useSourceCodeEditorAutoApply stays idle when auto-apply is disabled in settings', async () => {
  const { dom, root } = createComponentRoot();
  let applyCount = 0;
  const props: HookHarnessProps = {
    enabled: false,
    currentCode: '<robot name="disabled" />',
    isDirty: true,
    isReadOnly: false,
    supportsValidation: true,
    validationErrorCount: 0,
    isValidationPending: false,
    isApplying: false,
    autoApplyBlockedCode: null,
    resolveDebounceMs: () => 20,
    onAutoApply: () => {
      applyCount += 1;
    },
  };

  try {
    await act(async () => {
      root.render(React.createElement(HookHarness, props));
    });

    await act(async () => {
      await wait(40);
    });

    assert.equal(applyCount, 0);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});
