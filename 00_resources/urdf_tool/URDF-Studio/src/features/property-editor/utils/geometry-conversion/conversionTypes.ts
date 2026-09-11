import type { GeometryType } from '@/types';
import type { MeshClearanceObstacle } from './meshAnalysis';

export interface ScalarInterval {
  start: number;
  end: number;
}

export interface GeomData {
  type?: GeometryType;
  dimensions?: { x: number; y: number; z: number };
  origin?: {
    xyz: { x: number; y: number; z: number };
    rpy: { r: number; p: number; y: number };
  };
}

export interface ConversionResult {
  type: GeometryType;
  dimensions: { x: number; y: number; z: number };
  origin: {
    xyz: { x: number; y: number; z: number };
    rpy: { r: number; p: number; y: number };
  };
}

export interface ConversionContext {
  siblingGeometries?: GeomData[];
  meshClearanceObstacles?: MeshClearanceObstacle[];
  fitVolumeWindowRatio?: number;
  overlapAllowanceRatio?: number;
}

export type MeshPrimaryAxis = 'x' | 'y' | 'z';
