type HtmlViewportSize = {
  width: number;
  height: number;
};

export function resolveUsdOffscreenFullscreenHtmlPosition(
  _object: unknown,
  _camera: unknown,
  size: HtmlViewportSize,
): [number, number] {
  return [size.width / 2, size.height / 2];
}
