"""Decode the tessellated display mesh saved in a SOLIDWORKS part.

SOLIDWORKS saves the triangles it uses for on-screen display in the
``Contents/DisplayLists`` stream. Each face is stored as triangle strips with
per-vertex normals and a stored bounding box. This module reads those strips
verbatim (no B-rep reconstruction) and validates every face record before
accepting it.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .container import read_streams

DISPLAY_STREAM = "Contents/DisplayLists"
_STRIP_LENGTHS_HEADER = struct.pack("<III", 4, 8, 2)


@dataclass
class Mesh:
    """Triangle mesh in the part's own coordinates (metres, Y up)."""

    positions: np.ndarray  # (n, 3) float64
    normals: np.ndarray  # (n, 3) float64, unit length
    triangles: np.ndarray  # (m, 3) int64, counter-clockwise
    faces: int = 0
    rejected: list = field(default_factory=list)

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.positions.min(0), self.positions.max(0)

    def summary(self) -> dict:
        lo, hi = self.bounds
        return {
            "faces": self.faces,
            "vertices": int(len(self.positions)),
            "triangles": int(len(self.triangles)),
            "size_m": (hi - lo).round(6).tolist(),
            "rejected_records": len(self.rejected),
        }


def _array(buf: bytes, at: int, stride: int, kind: int) -> tuple[int, int, int]:
    """Read a typed array header; return (data start, data end, count)."""
    if at < 0 or at + 16 > len(buf):
        raise ValueError("array header outside stream")
    s, k, t, n = struct.unpack_from("<IIII", buf, at)
    end = at + 16 + s * n
    if (s, k, t) != (stride, kind, 2) or n > 2_000_000 or end > len(buf):
        raise ValueError("invalid array header")
    return at + 16, end, n


def _strips_to_triangles(lengths: np.ndarray, tokens: np.ndarray) -> np.ndarray:
    triangles = []
    v = t = 0
    for n in map(int, lengths):
        if tokens[t] != 1:
            raise ValueError("unexpected strip control token")
        t += 2  # control token + first edge flag
        for i in range(2, n):
            # Alternate winding so every triangle in the strip faces the same way.
            triangles.append((v + i - 2, v + i - 1, v + i) if i % 2 == 0 else (v + i - 1, v + i - 2, v + i))
            t += 2  # two edge-visibility flags per added vertex
        v += n
    return np.asarray(triangles, dtype=np.int64).reshape(-1, 3)


def _parse_face(buf: bytes, offset: int):
    st, end, n_strips = _array(buf, offset, 4, 8)
    lengths = np.frombuffer(buf, "<u4", n_strips, st)
    st, end, n_vert = _array(buf, end, 12, 100)
    vertices = np.frombuffer(buf, "<f4", n_vert * 3, st).reshape(-1, 3).astype(np.float64)
    st, end, n_norm = _array(buf, end, 12, 100)
    normals = np.frombuffer(buf, "<f4", n_norm * 3, st).reshape(-1, 3).astype(np.float64)
    st, end, n_tok = _array(buf, end, 4, 8)
    tokens = np.frombuffer(buf, "<u4", n_tok, st)
    st, end, n_tok_len = _array(buf, end, 4, 8)
    token_lengths = np.frombuffer(buf, "<u4", n_tok_len, st)
    st, end, n_pad = _array(buf, end, 1, 8)

    if n_strips == 0 or np.any(lengths < 3) or int(lengths.sum()) != n_vert:
        raise ValueError("strip lengths do not partition the vertices")
    if n_vert != n_norm or n_strips != n_tok_len or n_tok != n_pad:
        raise ValueError("array lengths disagree")
    if np.any(token_lengths != 2 * lengths - 2) or int(token_lengths.sum()) != n_tok:
        raise ValueError("edge token lengths disagree")
    if not (np.isfinite(vertices).all() and np.isfinite(normals).all()):
        raise ValueError("non-finite geometry")
    if np.max(np.abs(np.linalg.norm(normals, axis=1) - 1)) > 1e-3:
        raise ValueError("normals are not unit length")
    if np.any(np.frombuffer(buf, "u1", n_pad, st)):
        raise ValueError("unexpected non-zero padding block")
    if end + 92 > len(buf):
        raise ValueError("missing stored bounds")
    center = np.array(struct.unpack_from("<ddd", buf, end + 12))
    hi = np.array(struct.unpack_from("<ddd", buf, end + 36))
    lo = np.array(struct.unpack_from("<ddd", buf, end + 60))
    radius = struct.unpack_from("<d", buf, end + 84)[0]
    if np.any(lo > hi) or not np.allclose(center, (lo + hi) / 2, atol=1e-12, rtol=0):
        raise ValueError("invalid stored bounds")
    if abs(radius - np.linalg.norm(hi - center)) > 1e-12:
        raise ValueError("invalid stored radius")
    if np.any(vertices < lo - 1e-5) or np.any(vertices > hi + 1e-5):
        raise ValueError("vertices outside stored bounds")
    return vertices, normals, _strips_to_triangles(lengths, tokens)


def parse_display_lists(stream: bytes) -> Mesh:
    """Parse every valid face record in a DisplayLists stream into one mesh."""
    positions, normals, triangles, rejected = [], [], [], []
    base = 0
    for hit in re.finditer(re.escape(_STRIP_LENGTHS_HEADER), stream):
        offset = hit.start()
        try:
            # A face record is a strip-length array followed by a vertex array;
            # other uint arrays inside a record also match the header, so skip them.
            _, end, _ = _array(stream, offset, 4, 8)
            _array(stream, end, 12, 100)
        except (ValueError, struct.error):
            continue
        try:
            v, n, t = _parse_face(stream, offset)
        except (ValueError, struct.error, IndexError) as exc:
            rejected.append({"offset": offset, "reason": str(exc)})
            continue
        positions.append(v)
        normals.append(n)
        triangles.append(t + base)
        base += len(v)
    if not positions:
        raise ValueError("no valid face records found in DisplayLists stream")
    return Mesh(
        positions=np.vstack(positions),
        normals=np.vstack(normals),
        triangles=np.vstack(triangles),
        faces=len(positions),
        rejected=rejected,
    )


def load_mesh(path: str | Path) -> Mesh:
    """Load the saved display mesh from a .SLDPRT file (read-only)."""
    streams = read_streams(Path(path).read_bytes())
    if DISPLAY_STREAM not in streams:
        raise ValueError(f"{path}: no {DISPLAY_STREAM} stream (part saved without display data?)")
    return parse_display_lists(streams[DISPLAY_STREAM])
