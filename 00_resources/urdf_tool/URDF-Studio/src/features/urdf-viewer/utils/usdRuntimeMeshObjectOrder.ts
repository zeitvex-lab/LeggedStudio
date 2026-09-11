export interface UsdRuntimeMeshTruthContext {
  proto?: {
    protoIndex?: number;
  } | null;
}

export interface UsdRuntimeMeshObjectOrderRenderInterface {
  getUrdfTruthLinkContextForMeshId?: (
    meshId: string,
    sectionName?: string,
  ) => UsdRuntimeMeshTruthContext | null | undefined;
}

export function parseUsdMeshObjectIndex(meshId: string): number | undefined {
  const match = String(meshId || '').match(/(?:\.proto_(?:mesh|[a-z]+)_id)(\d+)$/i);
  if (!match) return undefined;

  const index = Number(match[1]);
  return Number.isInteger(index) && index >= 0 ? index : undefined;
}

export function resolveUsdVisualMeshObjectOrder({
  renderInterface,
  meshId,
  fallbackOrder,
}: {
  renderInterface: UsdRuntimeMeshObjectOrderRenderInterface | null | undefined;
  meshId: string;
  fallbackOrder: number;
}): number {
  const parsedIndex = parseUsdMeshObjectIndex(meshId);
  if (typeof parsedIndex === 'number' && Number.isInteger(parsedIndex)) {
    return parsedIndex;
  }

  const truthContext = renderInterface?.getUrdfTruthLinkContextForMeshId?.(meshId, 'visuals');
  const truthIndex = truthContext?.proto?.protoIndex;
  if (typeof truthIndex === 'number' && Number.isInteger(truthIndex) && truthIndex >= 0) {
    return truthIndex;
  }

  return fallbackOrder;
}
