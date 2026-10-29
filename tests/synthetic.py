"""Build tiny synthetic SOLIDWORKS-like data so tests never need proprietary CAD files."""
import struct
import zlib

import numpy as np

from cad_to_usd.container import RECORD_SIGNATURE, swap_nibbles


def record(name: str, payload: bytes) -> bytes:
    """One compressed stream record in the layout read by read_streams()."""
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = comp.compress(payload) + comp.flush()
    raw_name = swap_nibbles(name.encode("ascii"))
    header = b"\x00" * 4 + RECORD_SIGNATURE + b"\x00" * 4
    header += struct.pack("<IIIHH", zlib.crc32(payload), len(body), len(payload), len(raw_name), 0)
    return header + raw_name + body


def _array(stride: int, kind: int, data: bytes, count: int) -> bytes:
    return struct.pack("<IIII", stride, kind, 2, count) + data


def square_face(z: float = 0.0) -> bytes:
    """A unit square in the XY plane stored as one 4-vertex triangle strip, normal +Z."""
    verts = np.array([[0, 0, z], [1, 0, z], [0, 1, z], [1, 1, z]], dtype="<f4")
    normals = np.tile(np.array([0, 0, 1], dtype="<f4"), (4, 1))
    lengths = np.array([4], dtype="<u4")
    tokens = np.array([1, 1, 1, 1, 1, 1], dtype="<u4")  # control, first edge, 2 flags x 2 vertices
    token_lengths = 2 * lengths - 2
    out = _array(4, 8, lengths.tobytes(), 1)
    out += _array(12, 100, verts.tobytes(), 4)
    out += _array(12, 100, normals.tobytes(), 4)
    out += _array(4, 8, tokens.tobytes(), len(tokens))
    out += _array(4, 8, token_lengths.tobytes(), 1)
    out += _array(1, 8, bytes(len(tokens)), len(tokens))
    lo, hi = np.array([0, 0, z], float), np.array([1, 1, z], float)
    center = (lo + hi) / 2
    out += b"\x00" * 12 + struct.pack("<ddd", *center) + struct.pack("<ddd", *hi) + struct.pack("<ddd", *lo)
    out += struct.pack("<d", np.linalg.norm(hi - center)) + b"\x00" * 8
    return out


def fake_part(faces: int = 2) -> bytes:
    stream = b"junk" + b"".join(square_face(z=float(i)) for i in range(faces))
    return b"\xde\xad" * 10 + record("Contents/DisplayLists", stream) + record("Contents/Other", b"x" * 50)
