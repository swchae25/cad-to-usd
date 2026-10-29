"""Dependency-light preview renderer (NumPy + Pillow).

A painter's-algorithm rasteriser with Lambert-style shading: good enough for
README images, contact sheets and turntable GIFs without a GPU or OpenGL.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .displaylists import Mesh

VIEWS = {"isometric": (-40, 22), "opposite": (140, 22), "side": (0, 0), "front": (90, 0)}


def _rotation(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = np.deg2rad(yaw_deg), np.deg2rad(pitch_deg)
    cy, sy, cp, sp = np.cos(y), np.sin(y), np.cos(p), np.sin(p)
    return np.array([[cy, 0, sy], [sp * sy, cp, -sp * cy], [-cp * sy, sp, cp * cy]])


def _normalised(mesh: Mesh) -> np.ndarray:
    p = mesh.positions - (mesh.positions.min(0) + mesh.positions.max(0)) / 2
    return p / max(np.ptp(p, axis=0).max(), 1e-12)


def render(
    mesh: Mesh,
    yaw: float = -40,
    pitch: float = 22,
    size: tuple[int, int] = (1600, 1100),
    background: str = "white",
    base_color: tuple[int, int, int] = (144, 157, 169),
    margin: float = 0.08,
) -> Image.Image:
    """Render one shaded view of the mesh (Y up, camera looking down -Z)."""
    w, h = size
    v = _normalised(mesh) @ _rotation(yaw, pitch).T
    span = np.maximum(np.ptp(v[:, :2], axis=0), 1e-12)
    scale = min(w * (1 - 2 * margin) / span[0], h * (1 - 2 * margin) / span[1])
    xy = v[:, :2] * np.array([scale, -scale])
    xy += np.array([w / 2, h / 2]) - (xy.min(0) + xy.max(0)) / 2

    tri = mesh.triangles
    q = v[tri]
    n = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    light = np.abs(n @ np.array([0.3, 0.6, 0.74162]))
    colors = (np.array(base_color) * (0.46 + 0.54 * light[:, None])).astype(int)

    img = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(img)
    for i in np.argsort(q[:, :, 2].mean(1)):  # far to near
        draw.polygon([tuple(xy[k]) for k in tri[i]], fill=tuple(colors[i]))
    return img


def render_views(mesh: Mesh, out_dir: str | Path, stem: str) -> list[Path]:
    out_dir = Path(out_dir)
    paths = []
    for view, (yaw, pitch) in VIEWS.items():
        path = out_dir / f"{stem}-{view}.png"
        render(mesh, yaw, pitch).save(path)
        paths.append(path)
    return paths


def turntable(mesh: Mesh, path: str | Path, frames: int = 36, size=(720, 540), pitch: float = 18) -> Path:
    """Save a looping GIF that spins the part about its vertical axis."""
    images = [
        render(mesh, -40 + 360 * k / frames, pitch, size=size).quantize(colors=96)
        for k in range(frames)
    ]
    path = Path(path)
    images[0].save(path, save_all=True, append_images=images[1:], duration=90, loop=0)
    return path
