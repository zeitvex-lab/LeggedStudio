export function supportsUsdWorkerRenderer(globalScope: typeof globalThis = globalThis): boolean {
  const canvasPrototype = globalScope.HTMLCanvasElement?.prototype as
    | { transferControlToOffscreen?: () => OffscreenCanvas }
    | undefined;

  return Boolean(
    globalScope.Worker
      && globalScope.OffscreenCanvas
      && canvasPrototype?.transferControlToOffscreen
      && globalScope.crossOriginIsolated,
  );
}
