"""Command line interface: ``cad-to-usd part.SLDPRT --usd --obj --render``."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .displaylists import load_mesh
from .export import write_obj, write_usda
from .render import render_views, turntable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cad-to-usd", description=__doc__)
    ap.add_argument("parts", nargs="+", type=Path, help=".SLDPRT files to convert")
    ap.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder")
    ap.add_argument("--usd", action="store_true", help="write <part>.usda")
    ap.add_argument("--obj", action="store_true", help="write <part>.obj")
    ap.add_argument("--render", action="store_true", help="write four PNG preview views")
    ap.add_argument("--turntable", action="store_true", help="write a spinning GIF")
    ap.add_argument("--up-axis", choices=["Y", "Z"], default="Z", help="up axis of exported files (default Z, as in Isaac Sim)")
    ap.add_argument("--rigid-body", action="store_true", help="add rigid-body physics and a convex-hull collider to the USD")
    ap.add_argument("--density", type=float, help="material density in kg/m^3 (e.g. 2700 for aluminium)")
    ap.add_argument("--collider", choices=["convexHull", "convexDecomposition", "none"], default="convexHull",
                    help="PhysX collision approximation (use convexDecomposition for frames and other concave parts)")
    args = ap.parse_args(argv)

    if not (args.usd or args.obj or args.render or args.turntable):
        args.usd = True
    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for part in args.parts:
        try:
            mesh = load_mesh(part)
        except (OSError, ValueError) as exc:
            print(f"[skip] {part.name}: {exc}")
            failed += 1
            continue
        stem = part.stem.replace(" ", "_")
        written = []
        if args.usd:
            written.append(write_usda(mesh, args.out / f"{stem}.usda", name=stem, up_axis=args.up_axis,
                                      rigid_body=args.rigid_body, density=args.density,
                                      collider=args.collider))
        if args.obj:
            written.append(write_obj(mesh, args.out / f"{stem}.obj", up_axis=args.up_axis))
        if args.render:
            written += render_views(mesh, args.out, stem)
        if args.turntable:
            written.append(turntable(mesh, args.out / f"{stem}-turntable.gif"))
        print(f"[ok]   {part.name}: {json.dumps(mesh.summary())}")
        for path in written:
            print(f"       -> {path}")
    return 1 if failed == len(args.parts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
