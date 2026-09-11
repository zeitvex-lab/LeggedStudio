import * as THREE from 'three';

/** A picked planar face sample in world space. */
export interface PlaneSample {
  point: THREE.Vector3;
  normal: THREE.Vector3;
}

/** A picked edge sample in world space (an infinite line through `origin`). */
export interface EdgeSample {
  origin: THREE.Vector3;
  direction: THREE.Vector3;
}

const DIRECTION_EPSILON = 1e-8;
const PARALLEL_EPSILON = 1e-7;

/**
 * Build a right-handed rigid frame (Matrix4) whose +Z axis is `normal`, located
 * at `point`. The tangent (X) axis follows `hintTangent` projected onto the
 * plane when supplied, otherwise an arbitrary stable axis is chosen. This is the
 * single source of truth for "point + normal -> joint origin frame".
 */
export function makeFrameFromPointAndNormal(
  point: THREE.Vector3,
  normal: THREE.Vector3,
  hintTangent?: THREE.Vector3,
): THREE.Matrix4 {
  const z = normal.clone();
  if (z.lengthSq() < DIRECTION_EPSILON) {
    z.set(0, 0, 1);
  } else {
    z.normalize();
  }

  let x = new THREE.Vector3();
  if (hintTangent) {
    x.copy(hintTangent).sub(z.clone().multiplyScalar(hintTangent.dot(z)));
  }
  if (x.lengthSq() < DIRECTION_EPSILON) {
    const fallback = Math.abs(z.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
    x = fallback.sub(z.clone().multiplyScalar(fallback.dot(z)));
  }
  x.normalize();

  const y = new THREE.Vector3().crossVectors(z, x).normalize();
  // Re-orthogonalize X to guarantee an exact orthonormal basis.
  x.crossVectors(y, z).normalize();

  return new THREE.Matrix4().makeBasis(x, y, z).setPosition(point);
}

/**
 * "Between two faces": frame located at the midpoint of the two picked points,
 * oriented by the averaged (hemisphere-aligned) normal. The result +Z follows
 * the FIRST plane's hemisphere (plane `a` is the orientation anchor), so the
 * pick order is significant; the alignment Flip control inverts it when needed.
 * Returns null when the combined normal is degenerate.
 */
export function computeMidPlaneFrame(a: PlaneSample, b: PlaneSample): THREE.Matrix4 | null {
  const normalA = a.normal.clone();
  const normalB = b.normal.clone();
  if (normalA.lengthSq() < DIRECTION_EPSILON || normalB.lengthSq() < DIRECTION_EPSILON) {
    return null;
  }
  normalA.normalize();
  normalB.normalize();

  // Align B into A's hemisphere so opposing face normals still average sensibly.
  if (normalA.dot(normalB) < 0) {
    normalB.negate();
  }

  const averageNormal = normalA.add(normalB);
  if (averageNormal.lengthSq() < DIRECTION_EPSILON) {
    return null;
  }
  averageNormal.normalize();

  const midpoint = a.point.clone().add(b.point).multiplyScalar(0.5);
  return makeFrameFromPointAndNormal(midpoint, averageNormal);
}

/**
 * "Two edges intersection": frame at the closest point between the two (possibly
 * skew) edge lines. +X follows edge A, +Z is the common perpendicular
 * (edgeA x edgeB). Returns null when the edges are parallel.
 */
export function computeEdgeIntersectionFrame(a: EdgeSample, b: EdgeSample): THREE.Matrix4 | null {
  const d1 = a.direction.clone();
  const d2 = b.direction.clone();
  if (d1.lengthSq() < DIRECTION_EPSILON || d2.lengthSq() < DIRECTION_EPSILON) {
    return null;
  }
  d1.normalize();
  d2.normalize();

  const perpendicular = new THREE.Vector3().crossVectors(d1, d2);
  if (perpendicular.lengthSq() < PARALLEL_EPSILON) {
    return null;
  }

  // Closest points between line A (a.origin + s d1) and line B (b.origin + t d2).
  const w0 = a.origin.clone().sub(b.origin);
  const aa = d1.dot(d1);
  const bb = d1.dot(d2);
  const cc = d2.dot(d2);
  const dd = d1.dot(w0);
  const ee = d2.dot(w0);
  const denom = aa * cc - bb * bb;
  if (Math.abs(denom) < PARALLEL_EPSILON) {
    return null;
  }

  const s = (bb * ee - cc * dd) / denom;
  const t = (aa * ee - bb * dd) / denom;
  const closestA = a.origin.clone().add(d1.clone().multiplyScalar(s));
  const closestB = b.origin.clone().add(d2.clone().multiplyScalar(t));
  const intersection = closestA.add(closestB).multiplyScalar(0.5);

  return makeFrameFromPointAndNormal(intersection, perpendicular.normalize(), d1);
}
