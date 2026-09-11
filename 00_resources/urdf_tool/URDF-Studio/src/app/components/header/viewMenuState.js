/**
 * @typedef {import('./types').HeaderViewConfig} HeaderViewConfig
 * @typedef {'showOptionsPanel' | 'showJointPanel' | 'showStructureGraph'} ViewConfigKey
 */

/**
 * Toggle visibility of a view panel.
 *
 * @param {HeaderViewConfig} current
 * @param {ViewConfigKey} key
 * @returns {HeaderViewConfig}
 */
export function toggleViewPanel(current, key) {
  return {
    ...current,
    [key]: !current[key],
  };
}

/**
 * The merged workspace exposes a single shared detail/options panel.
 *
 * @param {HeaderViewConfig} current
 * @param {boolean} visible
 * @returns {HeaderViewConfig}
 */
export function setOptionsPanelVisibility(current, visible) {
  return {
    ...current,
    showOptionsPanel: visible,
  };
}

/**
 * Toggling the options entry should update the shared detail panel.
 *
 * @param {HeaderViewConfig} current
 * @returns {HeaderViewConfig}
 */
export function toggleOptionsPanel(current) {
  const nextVisible = !current.showOptionsPanel;

  return setOptionsPanelVisibility(current, nextVisible);
}
