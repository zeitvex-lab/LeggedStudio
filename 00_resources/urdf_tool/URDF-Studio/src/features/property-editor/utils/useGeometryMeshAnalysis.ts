import { useEffect, useMemo, useRef } from 'react';

import { scheduleFailFastInDev } from '@/core/utils/runtimeDiagnostics';
import { GeometryType, type UrdfVisual } from '@/types';

import { type MeshAnalysis, type MeshAnalysisOptions } from './geometryConversion';
import { analyzeMeshBatchWithWorker } from './meshAnalysisWorkerBridge';

const GEOMETRY_EDITOR_MESH_ANALYSIS_OPTIONS = {
  includePrimitiveFits: true,
  includeSurfacePoints: false,
  pointCollectionLimit: 2048,
} satisfies MeshAnalysisOptions;

type GeometryMeshAnalysisGeometry = Pick<UrdfVisual, 'meshPath' | 'type'> & {
  dimensions?: UrdfVisual['dimensions'];
};

export function createGeometryMeshAnalysisKey(
  geometry: Pick<UrdfVisual, 'meshPath'> & { dimensions?: UrdfVisual['dimensions'] },
  sourceFilePath?: string,
): string {
  return [
    geometry.meshPath ?? '',
    geometry.dimensions?.x ?? 1,
    geometry.dimensions?.y ?? 1,
    geometry.dimensions?.z ?? 1,
    sourceFilePath ?? '',
  ].join('::');
}

async function analyzeMeshGeometry(
  geometry: GeometryMeshAnalysisGeometry,
  assets: Record<string, string>,
  sourceFilePath?: string,
  signal?: AbortSignal,
): Promise<MeshAnalysis | null> {
  if (geometry.type !== GeometryType.MESH || !geometry.meshPath) {
    return null;
  }

  const analysisKey = createGeometryMeshAnalysisKey(geometry, sourceFilePath);
  const workerResults = await analyzeMeshBatchWithWorker({
    assets,
    tasks: [
      {
        targetId: analysisKey,
        cacheKey: analysisKey,
        meshPath: geometry.meshPath,
        dimensions: geometry.dimensions,
        sourceFilePath,
      },
    ],
    options: GEOMETRY_EDITOR_MESH_ANALYSIS_OPTIONS,
    signal,
  });

  return workerResults[analysisKey] ?? null;
}

function isMeshAnalysisWorkerUnavailable(error: unknown): boolean {
  const message =
    error instanceof Error
      ? `${error.message} ${error.cause instanceof Error ? error.cause.message : ''}`
      : String(error);

  return /(?:web worker is not available|mesh analysis worker is unavailable)/i.test(message);
}

export function useGeometryMeshAnalysis({
  assets,
  geometry,
  sourceFilePath,
}: {
  assets: Record<string, string>;
  geometry: GeometryMeshAnalysisGeometry;
  sourceFilePath?: string;
}) {
  const meshAnalysisRef = useRef<MeshAnalysis | null>(null);
  const meshAnalysisKeyRef = useRef<string | null>(null);
  const meshAnalysisCacheRef = useRef<Record<string, MeshAnalysis | null>>({});
  const meshAnalysisPromiseCacheRef = useRef<Partial<Record<string, Promise<MeshAnalysis | null>>>>(
    {},
  );
  const geometryDimensionX = geometry.dimensions?.x;
  const geometryDimensionY = geometry.dimensions?.y;
  const geometryDimensionZ = geometry.dimensions?.z;

  const geometryForAnalysis = useMemo<GeometryMeshAnalysisGeometry>(
    () => ({
      type: geometry.type,
      meshPath: geometry.meshPath,
      dimensions:
        geometryDimensionX !== undefined ||
        geometryDimensionY !== undefined ||
        geometryDimensionZ !== undefined
        ? {
            x: geometryDimensionX ?? 1,
            y: geometryDimensionY ?? 1,
            z: geometryDimensionZ ?? 1,
          }
        : undefined,
    }),
    [
      geometryDimensionX,
      geometryDimensionY,
      geometryDimensionZ,
      geometry.meshPath,
      geometry.type,
    ],
  );
  const currentAnalysisKey = useMemo(
    () => createGeometryMeshAnalysisKey(geometryForAnalysis, sourceFilePath),
    [geometryForAnalysis, sourceFilePath],
  );

  useEffect(() => {
    if (geometryForAnalysis.type !== GeometryType.MESH || !geometryForAnalysis.meshPath) {
      return;
    }

    const analysisKey = currentAnalysisKey;
    if (meshAnalysisKeyRef.current === analysisKey && meshAnalysisRef.current) {
      return;
    }
    if (meshAnalysisPromiseCacheRef.current[analysisKey]) {
      return;
    }

    meshAnalysisKeyRef.current = analysisKey;
    meshAnalysisRef.current = null;
    const controller = new AbortController();
    const analysisPromise = analyzeMeshGeometry(
      geometryForAnalysis,
      assets,
      sourceFilePath,
      controller.signal,
    );
    meshAnalysisPromiseCacheRef.current[analysisKey] = analysisPromise;

    void analysisPromise
      .then((analysis) => {
        if (meshAnalysisPromiseCacheRef.current[analysisKey] === analysisPromise) {
          delete meshAnalysisPromiseCacheRef.current[analysisKey];
        }
        if (!controller.signal.aborted) {
          meshAnalysisCacheRef.current[analysisKey] = analysis;
          meshAnalysisRef.current = analysis;
        }
      })
      .catch((error) => {
        if (meshAnalysisPromiseCacheRef.current[analysisKey] === analysisPromise) {
          delete meshAnalysisPromiseCacheRef.current[analysisKey];
        }
        if (!controller.signal.aborted && isMeshAnalysisWorkerUnavailable(error)) {
          meshAnalysisCacheRef.current[analysisKey] = null;
          meshAnalysisRef.current = null;
          return;
        }
        if (!controller.signal.aborted) {
          scheduleFailFastInDev(
            'GeometryEditor:meshAnalysis',
            new Error(`Failed to analyze mesh geometry for ${geometryForAnalysis.meshPath}.`, {
              cause: error,
            }),
          );
        }
      });

    return () => {
      controller.abort();
    };
  }, [assets, currentAnalysisKey, geometryForAnalysis, sourceFilePath]);

  const resolveMeshAnalysisForGeometry = async (
    targetGeometry: UrdfVisual,
  ): Promise<MeshAnalysis | null> => {
    if (targetGeometry.type !== GeometryType.MESH || !targetGeometry.meshPath) {
      return null;
    }

    const analysisKey = createGeometryMeshAnalysisKey(targetGeometry, sourceFilePath);
    if (analysisKey in meshAnalysisCacheRef.current) {
      return meshAnalysisCacheRef.current[analysisKey];
    }
    if (meshAnalysisKeyRef.current === analysisKey && meshAnalysisRef.current) {
      meshAnalysisCacheRef.current[analysisKey] = meshAnalysisRef.current;
      return meshAnalysisRef.current;
    }

    const pendingAnalysis = meshAnalysisPromiseCacheRef.current[analysisKey];
    if (pendingAnalysis) {
      const analysis = await pendingAnalysis.catch((error) => {
        if (isMeshAnalysisWorkerUnavailable(error)) {
          return null;
        }
        throw error;
      });
      meshAnalysisCacheRef.current[analysisKey] = analysis;
      return analysis;
    }

    const analysisPromise = analyzeMeshGeometry(targetGeometry, assets, sourceFilePath);
    meshAnalysisPromiseCacheRef.current[analysisKey] = analysisPromise;
    try {
      const analysis = await analysisPromise.catch((error) => {
        if (isMeshAnalysisWorkerUnavailable(error)) {
          return null;
        }
        throw error;
      });
      meshAnalysisCacheRef.current[analysisKey] = analysis;

      if (
        targetGeometry.meshPath === geometryForAnalysis.meshPath &&
        analysisKey === currentAnalysisKey
      ) {
        meshAnalysisKeyRef.current = analysisKey;
        meshAnalysisRef.current = analysis;
      }

      return analysis;
    } finally {
      if (meshAnalysisPromiseCacheRef.current[analysisKey] === analysisPromise) {
        delete meshAnalysisPromiseCacheRef.current[analysisKey];
      }
    }
  };

  return {
    meshAnalysisRef,
    resolveMeshAnalysisForGeometry,
  };
}
