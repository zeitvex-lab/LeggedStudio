export function encodeTextAssetAsDataUrl(content: string): string {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(content)}`;
}

export function mergeTextMeshSidecarAssets(
  assets: Record<string, string>,
  allFileContents: Record<string, string>,
): Record<string, string> {
  const mergedAssets = { ...assets };

  Object.entries(allFileContents).forEach(([path, content]) => {
    const lowerPath = path.toLowerCase();
    if (!(lowerPath.endsWith('.obj') || lowerPath.endsWith('.mtl') || lowerPath.endsWith('.dae'))) {
      return;
    }

    if (!mergedAssets[path]) {
      mergedAssets[path] = encodeTextAssetAsDataUrl(content);
    }
  });

  return mergedAssets;
}
