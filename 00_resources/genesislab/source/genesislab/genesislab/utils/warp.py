"""Geometry utility functions for GenesisLab (Warp-free).

This module provides a minimal subset of the Warp-based helpers used in the
terrain utilities, implemented purely with NumPy, PyTorch and Trimesh so that
GenesisLab does not depend on Warp at runtime.

The API intentionally mirrors the functions used in IsaacLab:

* :func:`convert_to_warp_mesh(points, indices, device)` – here returns a
  lightweight ``SimpleMesh`` container.
* :func:`raycast_mesh(starts, directions, mesh, ...)` – implemented via
  Trimesh ray casting and returning the same tuple structure as the original
  helper: ``(hits, distance, normal, face_id)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import torch
import trimesh  # type: ignore[import]


@dataclass
class SimpleMesh:
    """Lightweight mesh container used by the terrain utilities.

    Attributes
    ----------
    vertices:
        Vertex positions as a tensor of shape ``(V, 3)``.
    faces:
        Triangle indices as a tensor of shape ``(F, 3)`` (long).
    """

    vertices: torch.Tensor
    faces: torch.Tensor

    @property
    def points(self) -> torch.Tensor:
        """Alias used by existing terrain utilities."""

        return self.vertices


def convert_to_warp_mesh(points: np.ndarray, indices: np.ndarray, device: str) -> SimpleMesh:
    """Create a simple mesh wrapper from vertices and triangle indices.

    This is a Warp-free replacement for IsaacLab's ``convert_to_warp_mesh``.
    """
    vertices = torch.as_tensor(points, dtype=torch.float32, device=device)
    faces = torch.as_tensor(indices, dtype=torch.long, device=device)
    return SimpleMesh(vertices=vertices, faces=faces)


def raycast_mesh(
    ray_starts: torch.Tensor,
    ray_directions: torch.Tensor,
    mesh: SimpleMesh,
    max_dist: float = 1e6,
    return_distance: bool = False,
    return_normal: bool = False,
    return_face_id: bool = False,
) -> Tuple[torch.Tensor, Optional[torch.Tensor], Optional[torch.Tensor], Optional[torch.Tensor]]:
    """Perform ray casting against a triangle mesh using Trimesh.

    Parameters
    ----------
    ray_starts:
        Ray origins, shape ``(N, 3)``.
    ray_directions:
        Ray directions, shape ``(N, 3)``.
    mesh:
        SimpleMesh instance produced by :func:`convert_to_warp_mesh`.
    max_dist:
        Maximum ray distance; intersections farther than this are ignored.
    return_distance:
        Whether to return distances along each ray.
    return_normal:
        Whether to return the hit face normal.
    return_face_id:
        Whether to return the hit face index.
    """
    device = ray_starts.device
    shape = ray_starts.shape
    n_rays = int(ray_starts.numel() // 3)

    starts_np = ray_starts.reshape(-1, 3).detach().cpu().numpy()
    dirs_np = ray_directions.reshape(-1, 3).detach().cpu().numpy()

    verts_np = mesh.vertices.detach().cpu().numpy()
    faces_np = mesh.faces.detach().cpu().numpy()

    tm = trimesh.Trimesh(vertices=verts_np, faces=faces_np, process=False)

    # Prefer fast embree-based intersector if available
    try:
        from trimesh.ray import ray_pyembree as ray_module  # type: ignore[import]
    except ImportError:
        from trimesh.ray import ray_triangle as ray_module  # type: ignore[no-redef]

    intersector = ray_module.RayMeshIntersector(tm)

    locations, index_ray, index_tri = intersector.intersects_location(
        ray_origins=starts_np,
        ray_directions=dirs_np,
        multiple_hits=False,
    )

    # Initialize outputs: default = no hit
    hits = torch.full((n_rays, 3), float("inf"), dtype=torch.float32, device=device)
    dist = torch.full((n_rays,), float("inf"), dtype=torch.float32, device=device) if return_distance else None
    normal = torch.full((n_rays, 3), float("inf"), dtype=torch.float32, device=device) if return_normal else None
    face_id = torch.full((n_rays,), -1, dtype=torch.int32, device=device) if return_face_id else None

    if len(index_ray) > 0:
        loc_t = torch.as_tensor(locations, dtype=torch.float32, device=device)
        idx_ray_t = torch.as_tensor(index_ray, dtype=torch.long, device=device)

        hits[idx_ray_t] = loc_t

        if return_distance:
            # Distance from start to hit
            start_hit = loc_t - torch.as_tensor(starts_np[index_ray], dtype=torch.float32, device=device)
            d = torch.linalg.norm(start_hit, dim=-1)
            # Clamp by max_dist
            valid = d <= max_dist
            d = torch.where(valid, d, torch.full_like(d, float("inf")))
            dist[idx_ray_t] = d

        if return_normal:
            face_normals = torch.as_tensor(tm.face_normals[index_tri], dtype=torch.float32, device=device)
            normal[idx_ray_t] = face_normals

        if return_face_id:
            face_id[idx_ray_t] = torch.as_tensor(index_tri, dtype=torch.int32, device=device)

    # Reshape hits back to original leading dimensions if needed
    hits = hits.view(*shape[:-1], 3)
    if dist is not None:
        dist = dist.view(-1)
    if normal is not None:
        normal = normal.view(*shape[:-1], 3)

    return hits, dist, normal, face_id


__all__ = ["SimpleMesh", "convert_to_warp_mesh", "raycast_mesh"]


