"""Write meshes as Wavefront OBJ or as USD (.usda) ready for NVIDIA Isaac Sim."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from .displaylists import Mesh

# SOLIDWORKS parts are Y-up; USD/Isaac Sim scenes are usually Z-up.
# A +90 degree rotation about X maps (x, y, z) -> (x, -z, y) and keeps winding.
COLLIDERS = ("convexHull", "convexDecomposition", "none")
_Y_UP_TO_Z_UP = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def to_up_axis(mesh: Mesh, up_axis: str) -> tuple[np.ndarray, np.ndarray]:
    """Return positions and normals rotated for the requested stage up axis."""
    if up_axis == "Y":
        return mesh.positions, mesh.normals
    if up_axis == "Z":
        return mesh.positions @ _Y_UP_TO_Z_UP.T, mesh.normals @ _Y_UP_TO_Z_UP.T
    raise ValueError("up_axis must be 'Y' or 'Z'")


def prim_name(text: str) -> str:
    """Turn a file name into a valid USD prim identifier."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", text).strip("_") or "part"
    return name if not name[0].isdigit() else f"_{name}"


def write_obj(mesh: Mesh, path: str | Path, up_axis: str = "Y") -> Path:
    """Write positions, vertex normals and triangles to an OBJ file."""
    pos, nrm = to_up_axis(mesh, up_axis)
    path = Path(path)
    with path.open("w", encoding="ascii") as f:
        f.write("# exported by cad-to-usd (units: metres)\n")
        np.savetxt(f, pos, fmt="v %.7g %.7g %.7g")
        np.savetxt(f, nrm, fmt="vn %.6g %.6g %.6g")
        idx = mesh.triangles + 1  # OBJ indices are 1-based; vertex i uses normal i
        np.savetxt(f, np.repeat(idx, 2, axis=1), fmt="f %d//%d %d//%d %d//%d")
    return path


def _usd_array(values: np.ndarray, fmt: str) -> str:
    if values.ndim == 1:
        return "[" + ", ".join(fmt % v for v in values) + "]"
    return "[" + ", ".join("(" + ", ".join(fmt % c for c in row) + ")" for row in values) + "]"


def write_usda(
    mesh: Mesh,
    path: str | Path,
    name: str = "Part",
    up_axis: str = "Z",
    rigid_body: bool = False,
    density: float | None = None,
    collider: str = "convexHull",
    color: tuple[float, float, float] = (0.58, 0.62, 0.66),
) -> Path:
    """Write the mesh as a USD ASCII layer.

    With ``rigid_body=True`` the root prim gets PhysicsRigidBodyAPI and the mesh
    gets a convex-hull collider, so the part falls, collides and can be pushed
    as soon as it is referenced into an Isaac Sim stage. ``density`` (kg/m^3)
    lets PhysX compute mass and inertia from the collision shape.
    ``collider`` is the PhysX mesh approximation: "convexHull" (fast, solid
    parts), "convexDecomposition" (concave parts such as frames) or "none".
    """
    if collider not in COLLIDERS:
        raise ValueError(f"collider must be one of {COLLIDERS}")
    pos, nrm = to_up_axis(mesh, up_axis)
    name = prim_name(name)
    lo, hi = pos.min(0), pos.max(0)

    root_schemas, root_attrs = [], []
    mesh_schemas, mesh_attrs = [], []
    if rigid_body:
        root_schemas.append("PhysicsRigidBodyAPI")
        mesh_schemas += ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]
        mesh_attrs.append(f'uniform token physics:approximation = "{collider}"')
        if density is not None:
            root_schemas.append("PhysicsMassAPI")
            root_attrs.append(f"float physics:density = {float(density):g}")

    def meta(schemas):
        if not schemas:
            return ""
        return " (\n    prepend apiSchemas = [" + ", ".join(f'"{s}"' for s in schemas) + "]\n)"

    lines = [
        "#usda 1.0",
        "(",
        f'    defaultPrim = "{name}"',
        "    metersPerUnit = 1",
        "    kilogramsPerUnit = 1",
        f'    upAxis = "{up_axis}"',
        '    doc = "Exported by cad-to-usd from a SOLIDWORKS saved display mesh"',
        ")",
        "",
        f'def Xform "{name}"{meta(root_schemas)}',
        "{",
        *[f"    {a}" for a in root_attrs],
        f'    def Mesh "geometry"{meta(mesh_schemas)}'.replace("\n", "\n    "),
        "    {",
        *[f"        {a}" for a in mesh_attrs],
        f"        float3[] extent = {_usd_array(np.array([lo, hi]), '%.7g')}",
        f"        int[] faceVertexCounts = {_usd_array(np.full(len(mesh.triangles), 3), '%d')}",
        f"        int[] faceVertexIndices = {_usd_array(mesh.triangles.ravel(), '%d')}",
        f"        normal3f[] normals = {_usd_array(nrm, '%.6g')} (",
        '            interpolation = "vertex"',
        "        )",
        "        uniform token orientation = \"rightHanded\"",
        f"        point3f[] points = {_usd_array(pos, '%.7g')}",
        f"        color3f[] primvars:displayColor = [({color[0]}, {color[1]}, {color[2]})]",
        '        uniform token subdivisionScheme = "none"',
        "    }",
        "}",
        "",
    ]
    path = Path(path)
    path.write_text("\n".join(lines), encoding="ascii")
    return path
