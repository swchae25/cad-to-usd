import numpy as np
import pytest

from cad_to_usd.displaylists import load_mesh, parse_display_lists
from synthetic import fake_part, square_face


def test_square_strip_becomes_two_triangles():
    mesh = parse_display_lists(square_face())
    assert mesh.faces == 1
    assert mesh.triangles.tolist() == [[0, 1, 2], [2, 1, 3]]
    assert not mesh.rejected


def test_triangle_winding_matches_stored_normals():
    mesh = parse_display_lists(square_face())
    q = mesh.positions[mesh.triangles]
    n = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])
    assert np.all(n @ np.array([0, 0, 1]) > 0)


def test_multiple_faces_are_merged_with_offset_indices(tmp_path):
    path = tmp_path / "part.SLDPRT"
    path.write_bytes(fake_part(faces=3))
    mesh = load_mesh(path)
    assert mesh.faces == 3
    assert len(mesh.positions) == 12 and len(mesh.triangles) == 6
    assert mesh.triangles.max() == 11
    assert mesh.summary()["size_m"] == [1.0, 1.0, 2.0]


def test_bad_bounds_are_rejected():
    face = bytearray(square_face())
    face[-25] ^= 0xFF  # corrupt the high byte of the stored lower bound (y)
    with pytest.raises(ValueError):
        parse_display_lists(bytes(face))


def test_file_without_display_data(tmp_path):
    path = tmp_path / "empty.SLDPRT"
    path.write_bytes(b"not a part")
    with pytest.raises(ValueError, match="DisplayLists"):
        load_mesh(path)
