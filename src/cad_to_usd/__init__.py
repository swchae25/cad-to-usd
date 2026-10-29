"""Extract saved tessellated meshes from SOLIDWORKS parts and export them for simulation."""

from .container import read_streams
from .displaylists import Mesh, parse_display_lists, load_mesh

__all__ = ["read_streams", "Mesh", "parse_display_lists", "load_mesh"]
__version__ = "0.1.0"
