"""Central configuration — reads from mqtt.yml.

Environment variables still override yml values as a fallback, preserving
backwards compatibility with any existing scripts that set them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH  = Path(__file__).parent / "mqtt.yml"

# ---------------------------------------------------------------------------
# Load YAML configs
# ---------------------------------------------------------------------------
with _CONFIG_PATH.open(encoding="utf-8") as _fh:
    _cfg = yaml.safe_load(_fh)

_sim_config_rel  = _cfg.get("sim_config")
_SIM_CONFIG_PATH = (_CONFIG_PATH.parent / _sim_config_rel).resolve() if _sim_config_rel else None

if _SIM_CONFIG_PATH and _SIM_CONFIG_PATH.exists():
    with _SIM_CONFIG_PATH.open(encoding="utf-8") as _fh:
        _sim_cfg = yaml.safe_load(_fh)
    _levels = _sim_cfg.get("state_updater", {}).get("flood_risk", {}).get("levels", [])
    # Levels are implicitly indexed 1-N (index 0 = Dry lives in default_level)
    FLOOD_LEVELS: dict[int, float] = {i + 1: float(lvl["threshold_start"]) for i, lvl in enumerate(_levels)}
    _dataset_name: str = _sim_cfg.get("input", {}).get("file", {}).get("dataset_name", "")
else:
    FLOOD_LEVELS = {1: 0.001, 2: 0.1, 3: 0.3, 4: 1.0, 5: 2.0}
    _dataset_name = ""

# Path to the water_depth layer folder, derived from the sim config dataset name.
# Used in file mode to load the initial flood state without relying on MQTT messages.
WATER_DEPTH_DATA_PATH:     str | None = str(_PROJECT_ROOT / "data" / _dataset_name / "water_depth") if _dataset_name else None
WATER_DEPTH_DATA_FILENAME: str        = "water_depth"

def _get(section: str, key: str, env_var: str, default):
    """Return yml value, overridden by env var if set."""
    import os
    val = _cfg.get(section, {}).get(key, default)
    return type(default)(os.environ[env_var]) if env_var in os.environ else val

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MAP_SIZE           = 9403
# Fallback path used only when InitAgent_Layer doesn't carry a color_palette.
COLOR_PALETTE_FILE = _PROJECT_ROOT / "data" / "data_29_10_2024" / "color_palette.json"
DEFAULT_DATA_ROOT   = _PROJECT_ROOT
PALETTE_MAX_VALUE   = 5
RENDER_ON_INIT_EOF  = True

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
BROKER_ADDRESS          = _get("mqtt", "host",                 "DANASIM_MQTT_HOST",            "localhost")
BROKER_PORT             = _get("mqtt", "port",                 "DANASIM_MQTT_PORT",            1883)
CLIENT_ID               = _get("mqtt", "client_id",           "DANASIM_MQTT_CLIENT_ID",       "Danasim_Monitor_Viewer")
SCENARIO_NAME           = _get("mqtt", "scenario",            "DANASIM_SCENARIO",             "scenario_local")
QOS_HANDSHAKE           = 1
QOS_EVENTS              = _get("mqtt", "qos_events",          "DANASIM_QOS_EVENTS",           1)
KEEPALIVE_SECONDS       = _get("mqtt", "keepalive",           "DANASIM_KEEPALIVE",            60)
HANDSHAKE_TIMEOUT_SECONDS = _get("mqtt", "handshake_timeout", "DANASIM_HANDSHAKE_TIMEOUT",    5.0)
HANDSHAKE_MAX_RETRIES   = _get("mqtt", "handshake_max_retries", "DANASIM_HANDSHAKE_MAX_RETRIES", 3)
FRAME_TIMEOUT_SECONDS   = _get("mqtt", "frame_timeout",        "DANASIM_FRAME_TIMEOUT",        720.0)

TOPIC_BASE             = f"FloodSim/{SCENARIO_NAME}"
TOPIC_EVENTS           = f"{TOPIC_BASE}/events"
TOPIC_SYSTEM           = f"{TOPIC_BASE}/system"
TOPIC_HANDSHAKE_PING   = f"{TOPIC_SYSTEM}/handshake/ping"
TOPIC_HANDSHAKE_PONG   = f"{TOPIC_SYSTEM}/handshake/pong"
TOPIC_CONTROL_EVENTS   = f"{TOPIC_BASE}/control/events"

# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------
RENDERER_TYPE        = _get("renderer", "type",           "DANASIM_RENDERER",          "csv")
DEPTH_PROVIDER_TYPE  = _get("renderer", "depth_provider", "DANASIM_DEPTH_PROVIDER",    "palette")
TERRAIN_LAYER_ID     = "topo_bathy"
WATER_DEPTH_LAYER_ID = "water_depth"
# "mqtt": initial flood state arrives via EYE_SetState_Layer messages (default)
# "file": initial flood state is read directly from the water_depth file on disk
INITIAL_STATE_SOURCE = _get("visualizer", "initial_state_source", "DANASIM_INITIAL_STATE_SOURCE", "mqtt")
IDLE_SLEEP_SECONDS   = 0.1
DEBUG_MODE           = True

# ---------------------------------------------------------------------------
# X3D renderer
# ---------------------------------------------------------------------------
X3D_SUBSAMPLE    = _get("x3d", "subsample",     "DANASIM_X3D_SUBSAMPLE",     1)
X3D_LOD_CHUNK    = _get("x3d", "lod_chunk",     "DANASIM_X3D_LOD_CHUNK",     256)
X3D_LOD_SUBSAMPLES = _cfg.get("x3d", {}).get("lod_subsamples", [1, 4, 16])
X3D_LOD_RANGES     = _cfg.get("x3d", {}).get("lod_ranges",     [5000.0, 20000.0])

# ---------------------------------------------------------------------------
# State mapping
# ---------------------------------------------------------------------------
STATE_TO_VALUE = {
    "DRY": 0,
    "VERY_SHALLOW": 1,
    "LOW_DEPTH": 2,
    "MEDIUM_DEPTH": 3,
    "FLOODED": 3,
    "HIGH_DEPTH": 4,
    "EXTREME_DEPTH": 5,
    "OBSTACLE_DESTROYED": 0,
    "OPEN": 0,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
