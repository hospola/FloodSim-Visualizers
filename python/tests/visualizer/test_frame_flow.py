import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from python.visualizer.simulation_app import SimulationApp
from python.visualizer.depth_providers.palette import PaletteDepthProvider
from python.visualizer.renderers.base import BaseRenderer


def _run_app_with_messages(messages: list) -> dict:
    """Feed messages into SimulationApp directly; return recorded call counts."""
    renderer = MagicMock(spec=BaseRenderer)
    depth_provider = PaletteDepthProvider()
    app = SimulationApp(renderer, depth_provider, MagicMock())
    for msg in messages:
        app.handle_event(msg)
    return {"snapshot_calls": renderer.save_snapshot.call_count}


def _init_messages():
    return [
        {
            "process": "InitMap_Config",
            "map": {"size_x": 10, "size_y": 10, "chunk_size": 2, "cell_resolution_m": 1.0},
        },
        {"process": "Init_EOF", "total_chunks_sent": 0},
    ]


def _layer_chunk(cells: dict):
    return {"process": "EYE_SetState_Layer", "changes": {"cells": cells}}


def _frame_sync():
    return {"process": "EYE_Frame_Sync", "simulation_time": "2026-01-01T00:00:00"}


def _sim_end():
    return {"process": "Sim_End", "sim_time_total": 1.0}


def test_render_only_on_frame_sync():
    """FrameEnd must NOT generate an image. EYE_Frame_Sync is the only render trigger."""
    messages = _init_messages() + [
        {"process": "FrameStart", "total_chunks": 1},
        _layer_chunk({"0": {"state": "FLOODED"}}),
        {"process": "FrameEnd"},
        # No EYE_Frame_Sync → no extra render beyond Init_EOF
        _sim_end(),
    ]
    result = _run_app_with_messages(messages)
    # Only Init_EOF should have triggered a snapshot (1 call)
    assert result["snapshot_calls"] == 1, (
        f"expected 1 snapshot (Init_EOF only), got {result['snapshot_calls']}"
    )
    print("PASS test_render_only_on_frame_sync")


def test_frame_sync_triggers_render():
    """EYE_Frame_Sync after FrameEnd must generate exactly one image."""
    messages = _init_messages() + [
        {"process": "FrameStart", "total_chunks": 1},
        _layer_chunk({"0": {"state": "FLOODED"}}),
        {"process": "FrameEnd"},
        _frame_sync(),
        _sim_end(),
    ]
    result = _run_app_with_messages(messages)
    # Init_EOF (1) + EYE_Frame_Sync (1) = 2 snapshots
    assert result["snapshot_calls"] == 2, (
        f"expected 2 snapshots (Init_EOF + EYE_Frame_Sync), got {result['snapshot_calls']}"
    )
    print("PASS test_frame_sync_triggers_render")


def test_bulk_apply_accumulates_across_chunks():
    """Changes from multiple chunks must all be present after FrameEnd."""
    from python.visualizer.data_model import SimulationGrid

    sim = SimulationGrid()
    sim.apply_init_map_config({
        "map": {"size_x": 5, "size_y": 5, "chunk_size": 1, "cell_resolution_m": 1.0}
    })

    chunk1 = {"0": {"state": "FLOODED"}}    # flat_index 0 → (row=0, col=0)
    chunk2 = {"6": {"state": "HIGH_DEPTH"}} # flat_index 6 → (row=1, col=1)

    pending = []
    pending.extend(sim.collect_from_layer_event(
        {"process": "EYE_SetState_Layer", "changes": {"cells": chunk1}}
    ))
    pending.extend(sim.collect_from_layer_event(
        {"process": "EYE_SetState_Layer", "changes": {"cells": chunk2}}
    ))

    assert sim.grid[0, 0] == 0, "grid should not be modified before apply_bulk_changes"
    assert sim.grid[1, 1] == 0, "grid should not be modified before apply_bulk_changes"

    sim.apply_bulk_changes(pending)

    assert sim.grid[0, 0] == 3, f"expected 3 (FLOODED), got {sim.grid[0, 0]}"
    assert sim.grid[1, 1] == 4, f"expected 4 (HIGH_DEPTH), got {sim.grid[1, 1]}"
    print("PASS test_bulk_apply_accumulates_across_chunks")


def run() -> int:
    tests = [
        test_render_only_on_frame_sync,
        test_frame_sync_triggers_render,
        test_bulk_apply_accumulates_across_chunks,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as exc:
            print(f"FAIL {test.__name__}: {exc}")
            failed += 1
    print(f"\n{'All' if not failed else failed} / {len(tests)} tests {'passed' if not failed else 'FAILED'}.")
    return failed


if __name__ == "__main__":
    raise SystemExit(run())
