"""Visualization runner — reads viz.yml and calls the right tool.

Usage (from project root):
    ./build/venvs/visualizer_env/bin/python -m python.visualizer.run_viz terrain
    ./build/venvs/visualizer_env/bin/python -m python.visualizer.run_viz flood
    ./build/venvs/visualizer_env/bin/python -m python.visualizer.run_viz x3d
    ./build/venvs/visualizer_env/bin/python -m python.visualizer.run_viz serve
    ./build/venvs/visualizer_env/bin/python -m python.visualizer.run_viz all
"""
from __future__ import annotations

import argparse
import http.server
import os
import sys
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent / "viz.yml"
_COMMANDS = ["terrain", "flood", "x3d", "serve", "all"]


def _load_config() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_terrain(cfg: dict) -> int:
    from .tools.generate_terrain_tiles import main
    p = cfg["paths"]
    t = cfg.get("terrain", {})
    argv = [
        "--idrisi", p["idrisi"],
        "--npy",    str(Path(p["csv_data"]) / "terrain.npy"),
        "--output", p["terrain_tiles"],
    ]
    if "min_zoom" in t:
        argv += ["--min-zoom", str(t["min_zoom"])]
    if "max_zoom" in t:
        argv += ["--max-zoom", str(t["max_zoom"])]
    return main(argv)


def run_flood(cfg: dict) -> int:
    from .tools.generate_flood_tiles import main
    p = cfg["paths"]
    argv = [
        "--csv",    p["csv_data"],
        "--georef", str(Path(p["terrain_tiles"]) / "georef.json"),
        "--output", p["flood_tiles"],
        "--palette", p["palette"],
    ]
    return main(argv)


def run_x3d(cfg: dict) -> int:
    from .tools.generate_x3d_heightmap import main
    p = cfg["paths"]
    x = cfg.get("x3d_heightmap", {})
    argv = [
        "--csv",    p["csv_data"],
        "--output", p["x3d_heightmap"],
        "--palette", p["palette"],
    ]
    if "resolution" in x:
        argv += ["--resolution", str(x["resolution"])]
    return main(argv)


def run_serve(cfg: dict) -> None:
    port = cfg.get("server", {}).get("port", 8080)
    os.chdir(Path(__file__).parents[2])  # serve from project root
    print(f"Serving at http://localhost:{port}")
    print("  X3D viewer:    http://localhost:{port}/outputs/x3d_heightmap/player.html".format(port=port))
    print("  CesiumJS viewer: http://localhost:{port}/viewer/index.html".format(port=port))
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("", port), handler) as httpd:
        httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DanaSim visualization runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=_COMMANDS,
        help="terrain: generate terrain tiles | "
             "flood: generate flood tiles | "
             "x3d: generate X3D heightmap viewer | "
             "serve: start HTTP server | "
             "all: terrain + flood + x3d",
    )
    args = parser.parse_args(argv)
    cfg = _load_config()

    if args.command == "terrain":
        return run_terrain(cfg)
    elif args.command == "flood":
        return run_flood(cfg)
    elif args.command == "x3d":
        return run_x3d(cfg)
    elif args.command == "serve":
        run_serve(cfg)
        return 0
    elif args.command == "all":
        for fn in (run_terrain, run_flood, run_x3d):
            rc = fn(cfg)
            if rc != 0:
                return rc
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
