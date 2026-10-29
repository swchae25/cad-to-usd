import numpy as np
import pytest

from cad_to_usd.displaylists import parse_display_lists
from cad_to_usd.export import _Y_UP_TO_Z_UP, prim_name, to_up_axis, write_obj, write_usda
from cad_to_usd.render import render
from synthetic import square_face


@pytest.fixture
def mesh():
    return parse_display_lists(square_face(z=0.5))


def test_up_axis_rotation_is_proper():
    assert np.isclose(np.linalg.det(_Y_UP_TO_Z_UP), 1.0)  # no mirroring, winding kept
    assert np.allclose(_Y_UP_TO_Z_UP @ [0, 1, 0], [0, 0, 1])  # part "up" becomes stage +Z


def test_y_up_is_unchanged(mesh):
    pos, _ = to_up_axis(mesh, "Y")
    assert np.array_equal(pos, mesh.positions)


def test_prim_name():
    assert prim_name("Gen 4 v23") == "Gen_4_v23"
    assert prim_name("4bar-link") == "_4bar_link"


def test_obj(mesh, tmp_path):
    lines = write_obj(mesh, tmp_path / "m.obj").read_text().splitlines()
    assert sum(l.startswith("v ") for l in lines) == 4
    assert sum(l.startswith("vn ") for l in lines) == 4
    assert "f 1//1 2//2 3//3" in lines


def test_usda_with_physics(mesh, tmp_path):
    text = write_usda(mesh, tmp_path / "m.usda", name="Rocker", rigid_body=True, density=2700).read_text()
    assert text.startswith("#usda 1.0")
    assert 'defaultPrim = "Rocker"' in text and 'upAxis = "Z"' in text
    assert '"PhysicsRigidBodyAPI", "PhysicsMassAPI"' in text
    assert "physics:density = 2700" in text
    assert 'physics:approximation = "convexHull"' in text
    assert "int[] faceVertexCounts = [3, 3]" in text


def test_usda_without_physics_has_no_schemas(mesh, tmp_path):
    text = write_usda(mesh, tmp_path / "m.usda").read_text()
    assert "apiSchemas" not in text and "physics:" not in text


def test_usda_loads_in_openusd(mesh, tmp_path):
    """Runs only where the official USD library (pip install usd-core) is available."""
    Usd = pytest.importorskip("pxr.Usd")
    from pxr import UsdGeom, UsdPhysics

    path = write_usda(mesh, tmp_path / "m.usda", name="Part", rigid_body=True, density=1000)
    stage = Usd.Stage.Open(str(path))
    root = stage.GetDefaultPrim()
    geom = UsdGeom.Mesh(stage.GetPrimAtPath("/Part/geometry"))
    assert root.HasAPI(UsdPhysics.RigidBodyAPI)
    assert len(geom.GetPointsAttr().Get()) == 4
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z


def test_render_produces_image(mesh):
    img = render(mesh, size=(200, 150))
    assert img.size == (200, 150)
    assert img.convert("L").getextrema()[0] < 255  # something was drawn
