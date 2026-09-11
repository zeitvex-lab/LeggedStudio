import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { ExportDialog, type ExportDialogConfig } from './ExportDialog.tsx';

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
  (globalThis as { HTMLInputElement?: typeof HTMLInputElement }).HTMLInputElement =
    dom.window.HTMLInputElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { PointerEvent?: typeof PointerEvent }).PointerEvent =
    dom.window.PointerEvent ?? dom.window.MouseEvent;
  (globalThis as { FocusEvent?: typeof FocusEvent }).FocusEvent = dom.window.FocusEvent;
  (globalThis as { KeyboardEvent?: typeof KeyboardEvent }).KeyboardEvent = dom.window.KeyboardEvent;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle =
    dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame =
    dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame =
    dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  if (!('attachEvent' in dom.window.HTMLElement.prototype)) {
    Object.defineProperty(dom.window.HTMLElement.prototype, 'attachEvent', {
      value: () => {},
      configurable: true,
    });
  }
  if (!('detachEvent' in dom.window.HTMLElement.prototype)) {
    Object.defineProperty(dom.window.HTMLElement.prototype, 'detachEvent', {
      value: () => {},
      configurable: true,
    });
  }

  return dom;
}

function createComponentRoot() {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  return { dom, container, root };
}

async function destroyComponentRoot(dom: JSDOM, root: Root) {
  await act(async () => {
    root.unmount();
  });
  dom.window.close();
}

async function renderExportDialog(
  root: Root,
  onExport: (config: ExportDialogConfig) => void,
  props: Partial<React.ComponentProps<typeof ExportDialog>> = {},
) {
  await act(async () => {
    root.render(
      React.createElement(ExportDialog, {
        onClose: () => {},
        onExport,
        lang: 'zh',
        canExportUsd: true,
        ...props,
      }),
    );
  });
}

function getButtonByText(container: Element, text: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.replace(/\s+/g, ' ').trim() === text,
  );
  assert.ok(button, `button "${text}" should exist`);
  return button as HTMLButtonElement;
}

function getRequiredElement<T extends Element>(
  container: ParentNode,
  selector: string,
  label: string,
): T {
  const element = container.querySelector(selector);
  assert.ok(element, `${label} should exist`);
  return element as T;
}

async function click(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

function getQualitySlider(container: Element): HTMLInputElement | null {
  return container.querySelector('input[type="range"]') as HTMLInputElement | null;
}

function setInputValue(input: HTMLInputElement, value: string) {
  const prototype = input.ownerDocument.defaultView?.HTMLInputElement.prototype;
  const valueSetter = prototype
    ? Object.getOwnPropertyDescriptor(prototype, 'value')?.set
    : undefined;

  assert.ok(valueSetter, 'HTMLInputElement value setter should exist');
  valueSetter.call(input, value);
}

async function changeRangeValue(input: HTMLInputElement, value: number) {
  await act(async () => {
    setInputValue(input, String(value));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

test('MJCF, URDF, SDF, and USD exports expose a custom compression mode with a slider', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, '自定义'));
    assert.ok(getQualitySlider(container), 'MJCF custom compression slider should render');

    await click(getButtonByText(container, 'URDF'));
    await click(getButtonByText(container, '自定义'));
    assert.ok(getQualitySlider(container), 'URDF custom compression slider should render');

    await click(getButtonByText(container, 'SDF'));
    await click(getButtonByText(container, '自定义'));
    assert.ok(getQualitySlider(container), 'SDF custom compression slider should render');

    await click(getButtonByText(container, 'USD'));
    await click(getButtonByText(container, '自定义'));
    assert.ok(getQualitySlider(container), 'USD custom compression slider should render');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('export dialog only shows file-format exports and keeps project export outside the dialog', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    const formatPicker = getRequiredElement<HTMLElement>(
      container,
      '[data-export-format-picker]',
      'format picker',
    );
    assert.doesNotMatch(formatPicker.textContent ?? '', /工程 \(\.usp\)/);
    assert.equal(container.querySelector('[data-project-export-card]'), null);
    assert.doesNotMatch(container.textContent ?? '', /导出当前工作区工程/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('USD export shows compression presets immediately without an extra toggle', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, 'USD'));

    assert.ok(getButtonByText(container, '不压缩'));
    assert.ok(getButtonByText(container, '低压缩'));
    assert.ok(getButtonByText(container, '中等'));
    assert.ok(getButtonByText(container, '自定义'));
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('SDF export explains that per-face box textures are flattened during export', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, 'SDF'));

    assert.match(
      container.textContent ?? '',
      /SDF 导出只会保留每个 visual 的单材质\/单贴图；box 六面不同贴图会在导出时自动合并为一张贴图/,
    );
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('USD export lets the user switch authored layer format to USDA', async () => {
  const { dom, container, root } = createComponentRoot();
  let exportedConfig: ExportDialogConfig | null = null as ExportDialogConfig | null;

  try {
    await renderExportDialog(root, (config) => {
      exportedConfig = config;
    });

    await click(getButtonByText(container, 'USD'));

    const fileFormatPicker = getRequiredElement<HTMLElement>(
      container,
      '[data-usd-file-format-picker]',
      'USD file format picker',
    );
    assert.match(fileFormatPicker.textContent ?? '', /USDUSDA/);

    await click(getButtonByText(container, 'USDA'));
    await click(getButtonByText(container, '导出 ZIP'));

    assert.ok(exportedConfig, 'USD export should submit a config');
    assert.equal(exportedConfig.usd.fileFormat, 'usda');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('USD export defaults to max mesh fidelity when the user exports without touching compression settings', async () => {
  const { dom, container, root } = createComponentRoot();
  let exportedConfig: ExportDialogConfig | null = null as ExportDialogConfig | null;

  try {
    await renderExportDialog(root, (config) => {
      exportedConfig = config;
    });

    await click(getButtonByText(container, 'USD'));
    await click(getButtonByText(container, '导出 ZIP'));

    assert.ok(exportedConfig, 'USD export should submit a config');
    assert.equal(exportedConfig.usd.compressMeshes, true);
    assert.equal(exportedConfig.usd.meshQuality, 100);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('USD export keeps the layer format and compression controls visually concise', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, 'USD'));

    const textContent = container.textContent ?? '';
    assert.doesNotMatch(textContent, /导出为 Isaac Sim 风格的分层包/);
    assert.doesNotMatch(textContent, /导出前简化 Mesh 三角面/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('USD layer format row keeps label and segmented buttons vertically centered', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, 'USD'));

    const fileFormatPicker = getRequiredElement<HTMLElement>(
      container,
      '[data-usd-file-format-picker]',
      'USD file format picker',
    );
    const row = fileFormatPicker.parentElement?.parentElement;
    assert.ok(row, 'USD file format row should exist');
    assert.match(row.className, /items-center/);

    const layerButtons = Array.from(fileFormatPicker.querySelectorAll('button'));
    assert.ok(layerButtons.length >= 2, 'USD layer format buttons should render');
    assert.match(layerButtons[0].className, /inline-flex/);
    assert.match(layerButtons[0].className, /items-center/);
    assert.match(layerButtons[0].className, /justify-center/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('custom compression keeps the slider visible and exports the selected MJCF quality', async () => {
  const { dom, container, root } = createComponentRoot();
  let exportedConfig: ExportDialogConfig | null = null as ExportDialogConfig | null;

  try {
    await renderExportDialog(root, (config) => {
      exportedConfig = config;
    });

    await click(getButtonByText(container, '自定义'));

    const slider = getQualitySlider(container);
    assert.ok(slider, 'custom compression slider should render');

    await changeRangeValue(slider, 42);
    assert.ok(
      getQualitySlider(container),
      'slider should remain visible after custom quality changes',
    );

    await click(getButtonByText(container, '导出 ZIP'));

    assert.ok(exportedConfig, 'export handler should receive the dialog config');
    assert.equal(exportedConfig.format, 'mjcf');
    assert.equal(exportedConfig.mjcf.compressSTL, true);
    assert.equal(exportedConfig.mjcf.stlQuality, 42);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('custom compression uses semantic space-vs-fidelity guidance instead of percentage wording', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, '自定义'));

    assert.match(container.textContent ?? '', /平衡/);
    assert.match(container.textContent ?? '', /更省空间/);
    assert.match(container.textContent ?? '', /更高保真/);
    assert.doesNotMatch(container.textContent ?? '', /更小体积/);
    assert.doesNotMatch(container.textContent ?? '', /更多细节/);
    assert.doesNotMatch(container.textContent ?? '', /\b50%\b/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('MJCF export label omits the XML suffix in the format picker', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    assert.match(container.textContent ?? '', /导出格式MJCFURDFXacroSDFUSD/);
    assert.doesNotMatch(container.textContent ?? '', /MJCF \/ XML/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('export format picker stays as a single compact row at the default dialog width', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    const formatPicker = getRequiredElement<HTMLElement>(
      container,
      '[data-export-format-picker]',
      'format picker',
    );
    assert.match(formatPicker.className, /grid-cols-5/);

    const mjcfButton = getButtonByText(container, 'MJCF');
    assert.doesNotMatch(mjcfButton.className, /flex-col/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('Xacro export moves ROS profile guidance into hover titles instead of inline copy', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {});

    await click(getButtonByText(container, 'Xacro'));

    const gazeboSwitch = getRequiredElement<HTMLButtonElement>(
      container,
      'button[role="switch"][aria-label="添加 Gazebo 控制标签"]',
      'Gazebo control toggle',
    );
    assert.equal(gazeboSwitch.getAttribute('aria-checked'), 'true');
    assert.match(container.textContent ?? '', /添加 Gazebo 控制标签/);

    const xacroRosVersionPicker = getRequiredElement<HTMLElement>(
      container,
      '[data-xacro-ros-version-picker]',
      'xacro ROS version picker',
    );
    assert.match(xacroRosVersionPicker.className, /grid-cols-1/);

    const ros2Button = getButtonByText(container, 'ROS2');
    assert.equal(
      ros2Button.getAttribute('title'),
      '使用 ROS2 ros2_control 约定。',
    );
    assert.equal(ros2Button.getAttribute('aria-pressed'), 'true');
    assert.match(ros2Button.className, /min-h-\[2\.5rem\]/);
    assert.doesNotMatch(ros2Button.className, /min-h-\[3\.15rem\]/);

    const gazeboBackendPicker = getRequiredElement<HTMLElement>(
      container,
      '[data-xacro-gazebo-backend-picker]',
      'xacro Gazebo backend picker',
    );
    assert.match(gazeboBackendPicker.className, /grid-cols-1/);

    const classicButton = getButtonByText(container, 'Gazebo Classic');
    assert.equal(
      classicButton.getAttribute('title'),
      '写入 Gazebo Classic 控制插件约定。',
    );
    assert.equal(classicButton.getAttribute('aria-pressed'), 'true');

    const gzButton = getButtonByText(container, 'Gazebo Sim (gz_ros2_control)');
    assert.equal(gzButton.getAttribute('title'), '写入现代 Gazebo / gz_ros2_control 控制插件约定。');
    assert.equal(gzButton.getAttribute('aria-pressed'), 'false');

    const xacroHintButton = Array.from(container.querySelectorAll('button[aria-label]')).find(
      (candidate) => candidate.getAttribute('aria-label')?.includes('导出为真正的 xacro'),
    );
    assert.ok(xacroHintButton, 'xacro static hint should still be available via hover');

    const hardwareSelect = container.querySelector('select');
    assert.ok(hardwareSelect, 'xacro hardware interface select should render');
    assert.equal(
      hardwareSelect?.getAttribute('title'),
      '写入每个 ros2_control joint 条目中的 ROS2 command_interface 名称。',
    );
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('Xacro export can omit Gazebo control tags', async () => {
  const { dom, container, root } = createComponentRoot();
  let exportedConfig: ExportDialogConfig | null = null as ExportDialogConfig | null;

  try {
    await renderExportDialog(root, (config) => {
      exportedConfig = config;
    });

    await click(getButtonByText(container, 'Xacro'));
    await click(
      getRequiredElement<HTMLButtonElement>(
        container,
        'button[role="switch"][aria-label="添加 Gazebo 控制标签"]',
        'Gazebo control toggle',
      ),
    );

    assert.equal(container.querySelector('[data-xacro-ros-version-picker]'), null);
    assert.equal(container.querySelector('[data-xacro-gazebo-backend-picker]'), null);
    assert.equal(container.querySelector('select'), null);

    await click(getButtonByText(container, '导出 ZIP'));

    assert.ok(exportedConfig, 'Xacro export should submit a config');
    assert.equal(exportedConfig.xacro.includeGazeboControl, false);
    assert.equal(exportedConfig.xacro.rosVersion, 'ros2');
    assert.equal(exportedConfig.xacro.gazeboBackend, 'classic');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('Xacro export maps ROS2 Gazebo Sim selection to the gz backend', async () => {
  const { dom, container, root } = createComponentRoot();
  let exportedConfig: ExportDialogConfig | null = null as ExportDialogConfig | null;

  try {
    await renderExportDialog(root, (config) => {
      exportedConfig = config;
    });

    await click(getButtonByText(container, 'Xacro'));
    await click(getButtonByText(container, 'Gazebo Sim (gz_ros2_control)'));
    await click(getButtonByText(container, '导出 ZIP'));

    assert.ok(exportedConfig, 'Xacro export should submit a config');
    assert.equal(exportedConfig.xacro.includeGazeboControl, true);
    assert.equal(exportedConfig.xacro.rosVersion, 'ros2');
    assert.equal(exportedConfig.xacro.gazeboBackend, 'gz');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('exporting state renders progress UI without crashing', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderExportDialog(root, () => {}, { isExporting: true });

    const exportingButton = getButtonByText(container, '导出中...');
    assert.equal(exportingButton.disabled, true);
    assert.match(container.textContent ?? '', /准备导出/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});
