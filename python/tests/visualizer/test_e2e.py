"""End-to-end tests — require a live Mosquitto broker on localhost:1883.

Mark: pytest.mark.e2e
Skip automatically if broker is not reachable.

Run explicitly with:
    pytest -m e2e python/tests/visualizer/test_e2e.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Broker availability check
# ---------------------------------------------------------------------------

def _broker_available() -> bool:
    try:
        import paho.mqtt.client as mqtt
        import socket
        with socket.create_connection(("localhost", 1883), timeout=1.0):
            return True
    except OSError:
        return False


broker_required = pytest.mark.skipif(
    not _broker_available(),
    reason="MQTT broker not available on localhost:1883",
)

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).parents[3]
PUBLISHER = str(PROJECT_ROOT / "python" / "tests" / "visualizer" / "publish_test_events.py")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_e2e(tmp_path: Path, scenario: str, renderer: str = "csv",
             frames: int = 2, rows: int = 8, cols: int = 10) -> dict:
    """
    Launches visualizer as subprocess, publishes test events, waits for clean exit.
    Returns dict with output paths for assertions.
    """
    out_dir = tmp_path / "sim_out"
    out_dir.mkdir()

    env = os.environ.copy()
    env["DANASIM_SCENARIO"] = scenario
    env["DANASIM_OUTPUT_FOLDER"] = str(out_dir)

    # Override renderer type via env var
    import python.visualizer.config as _cfg  # noqa: F401 — ensure config loaded
    env["DANASIM_RENDERER"] = renderer

    subscriber = subprocess.Popen(
        [PYTHON, "-m", "python.visualizer.main"],
        env=env,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    time.sleep(1.5)  # let subscriber connect and subscribe

    publisher = subprocess.run(
        [
            PYTHON, PUBLISHER,
            "--scenario", scenario,
            "--host", "localhost",
            "--port", "1883",
            "--rows", str(rows),
            "--cols", str(cols),
            "--frames", str(frames),
            "--wet-cells", "5",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )

    try:
        sub_out, _ = subscriber.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        subscriber.kill()
        sub_out, _ = subscriber.communicate()

    return {
        "sub_out": sub_out,
        "pub_out": publisher.stdout,
        "pub_rc": publisher.returncode,
        "out_dir": out_dir,
    }


# ===========================================================================
# E2E: CSV renderer
# ===========================================================================

@broker_required
@pytest.mark.e2e
class TestE2ECSV:
    def test_clean_exit(self, tmp_path: Path) -> None:
        """Visualizer exits cleanly after Sim_End."""
        result = _run_e2e(tmp_path, "e2e_csv_exit")
        assert "Clean exit after Sim_End" in result["sub_out"], \
            f"Subscriber output: {result['sub_out']}"

    def test_meta_json_written(self, tmp_path: Path) -> None:
        """meta.json is created with correct grid dimensions."""
        result = _run_e2e(tmp_path, "e2e_csv_meta")
        meta_path = result["out_dir"] / "csv_data" / "meta.json"
        assert meta_path.exists(), "meta.json not found"
        meta = json.loads(meta_path.read_text())
        assert meta["rows"] > 0
        assert meta["cols"] > 0
        assert meta["cell_size_m"] == pytest.approx(5.0)

    def test_frame_csv_written(self, tmp_path: Path) -> None:
        """At least one step_XXXXX.csv is created."""
        result = _run_e2e(tmp_path, "e2e_csv_frames")
        csv_dir = result["out_dir"] / "csv_data"
        frames = sorted(csv_dir.glob("step_?????.csv"))
        assert len(frames) >= 1, f"No CSV frames found in {csv_dir}"

    def test_terrain_npy_written(self, tmp_path: Path) -> None:
        """terrain.npy is created."""
        result = _run_e2e(tmp_path, "e2e_csv_terrain")
        assert (result["out_dir"] / "csv_data" / "terrain.npy").exists()


# ===========================================================================
# E2E: X3D renderer
# ===========================================================================

@broker_required
@pytest.mark.e2e
class TestE2ECSVContent:
    def test_csv_has_correct_header(self, tmp_path: Path) -> None:
        """CSV frames contain the correct column header."""
        result = _run_e2e(tmp_path, "e2e_csv_header")
        frames = sorted((result["out_dir"] / "csv_data").glob("step_?????.csv"))
        assert frames, "No CSV frames found"
        header_lines = [l for l in frames[0].read_text().splitlines()
                        if not l.startswith("#")]
        assert header_lines[0] == "row,col,flood_risk"

    def test_csv_wet_cells_have_valid_flood_risk(self, tmp_path: Path) -> None:
        """All flood_risk values in CSVs are in range 1–5."""
        result = _run_e2e(tmp_path, "e2e_csv_values")
        csv_dir = result["out_dir"] / "csv_data"
        for csv_path in sorted(csv_dir.glob("step_?????.csv")):
            for line in csv_path.read_text().splitlines():
                if line.startswith("#") or line.startswith("row"):
                    continue
                parts = line.split(",")
                assert len(parts) == 3, f"Unexpected line: {line}"
                flood_risk = int(parts[2])
                assert 1 <= flood_risk <= 5, f"flood_risk out of range: {flood_risk}"

    def test_multiple_frames_written(self, tmp_path: Path) -> None:
        """N simulation frames produce N step_XXXXX.csv files."""
        n_frames = 3
        result = _run_e2e(tmp_path, "e2e_csv_multi", frames=n_frames)
        csv_dir = result["out_dir"] / "csv_data"
        frames = sorted(csv_dir.glob("step_?????.csv"))
        # init snapshot + n_frames simulation frames
        assert len(frames) >= n_frames, \
            f"Expected >= {n_frames} frames, got {len(frames)}"

    def test_meta_json_dimensions_match_publisher(self, tmp_path: Path) -> None:
        """meta.json dimensions match what the publisher sent."""
        result = _run_e2e(tmp_path, "e2e_csv_dims", rows=6, cols=8)
        meta = json.loads((result["out_dir"] / "csv_data" / "meta.json").read_text())
        assert meta["rows"] == 6
        assert meta["cols"] == 8


@broker_required
@pytest.mark.e2e
class TestE2EX3D:
    def test_player_html_written(self, tmp_path: Path) -> None:
        """player.html is generated after Sim_End."""
        result = _run_e2e(tmp_path, "e2e_x3d_player", renderer="x3d")
        player = result["out_dir"] / "x3d_heightmap" / "player.html"
        assert player.exists(), "player.html not found"

    def test_manifest_closed(self, tmp_path: Path) -> None:
        """manifest.json is marked live=false after Sim_End."""
        result = _run_e2e(tmp_path, "e2e_x3d_manifest", renderer="x3d")
        manifest_path = result["out_dir"] / "x3d_heightmap" / "flood" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["live"] is False

    def test_flood_pngs_written(self, tmp_path: Path) -> None:
        """At least one flood PNG is written per frame."""
        result = _run_e2e(tmp_path, "e2e_x3d_pngs", renderer="x3d")
        flood_dir = result["out_dir"] / "x3d_heightmap" / "flood"
        pngs = sorted(flood_dir.glob("step_?????.png"))
        assert len(pngs) >= 1, f"No flood PNGs found in {flood_dir}"

    def test_png_count_matches_manifest(self, tmp_path: Path) -> None:
        """Number of PNGs in flood/ matches frames listed in manifest.json."""
        n_frames = 2
        result = _run_e2e(tmp_path, "e2e_x3d_count", renderer="x3d", frames=n_frames)
        flood_dir = result["out_dir"] / "x3d_heightmap" / "flood"
        pngs = sorted(flood_dir.glob("step_?????.png"))
        manifest = json.loads((flood_dir / "manifest.json").read_text())
        assert len(pngs) == len(manifest["frames"]), \
            f"PNG count {len(pngs)} != manifest frames {len(manifest['frames'])}"

    def test_js_assets_present(self, tmp_path: Path) -> None:
        """js/ directory with app.js is present alongside player.html."""
        result = _run_e2e(tmp_path, "e2e_x3d_js", renderer="x3d")
        out = result["out_dir"] / "x3d_heightmap"
        assert (out / "js" / "app.js").exists()
        assert (out / "js" / "live.js").exists()
