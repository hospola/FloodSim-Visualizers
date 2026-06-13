
import numpy as np
import logging
from pathlib import Path

from .idrisi_io import IdrisiIO
from . import config

class SimulationGrid:
    """
    Manages the state of the simulation grid.
    """

    def __init__(self):
        # Store palette levels as uint8 values.
        self.grid = np.zeros((config.MAP_SIZE, config.MAP_SIZE), dtype=np.uint8)
        self.terrain_heights: np.ndarray | None = None  # float32, flat (rows*cols,)
        self.color_palette: list[dict] | None = None  # raw `color_palette` from InitAgent_Layer, if provided
        self.water_depths_m = np.zeros((config.MAP_SIZE, config.MAP_SIZE), dtype=np.float32)
        self.has_new_data = False
        self.map_config = {
            "size_x": config.MAP_SIZE,
            "size_y": config.MAP_SIZE,
            "chunk_size": None,
            "cell_resolution_m": None,
        }
        self.initialization = {
            "map_config_received": False,
            "init_layers_received": 0,
            "init_agent_complete": False,
            "init_complete": False,
        }
        self._logger = logging.getLogger(__name__)

    @property
    def cell_size_m(self) -> float:
        return float(self.map_config.get("cell_resolution_m") or 1.0)

    def apply_init_map_config(self, event: dict) -> bool:
        map_cfg = event.get("map", {})
        size_x = int(map_cfg.get("size_x", self.grid.shape[1]))
        size_y = int(map_cfg.get("size_y", self.grid.shape[0]))

        if size_x <= 0 or size_y <= 0:
            self._logger.error("Invalid InitMap_Config sizes: size_x=%s size_y=%s", size_x, size_y)
            return False

        if self.grid.shape != (size_y, size_x):
            self._logger.info("Reallocating grid to %sx%s from InitMap_Config", size_x, size_y)
            self.grid = np.zeros((size_y, size_x), dtype=np.uint8)
            self.water_depths_m = np.zeros((size_y, size_x), dtype=np.float32)

        self.map_config.update(
            {
                "size_x": size_x,
                "size_y": size_y,
                "chunk_size": map_cfg.get("chunk_size"),
                "cell_resolution_m": map_cfg.get("cell_resolution_m"),
            }
        )
        self.initialization["map_config_received"] = True
        return True

    def apply_event(self, event: dict) -> bool:
        """Dispatch a supported MQTT event into the grid state.

        Returns True when the event modified the grid.
        """
        process = event.get("process")

        if process == "EYE_SetState_Layer":
            return self.update_from_layer_event(event)

        if process == "EYE_SetState":
            return self.update_from_object_event(event)

        return False

    def apply_init_agent_layer(self, event: dict) -> bool:
        data_path = event.get("data_path")
        data_filename = event.get("data_filename")
        layer_id = event.get("id")

        color_palette = event.get("color_palette")
        if color_palette is not None:
            self.color_palette = color_palette

        if not data_path or not data_filename or not layer_id:
            self._logger.error(
                "InitAgent_Layer requires data_path, data_filename and id. "
                "Received data_path=%s data_filename=%s id=%s",
                data_path,
                data_filename,
                layer_id,
            )
            return False

        if layer_id == config.TERRAIN_LAYER_ID:
            raw = self._load_raw_floats_from_data_path(data_path, data_filename)
            if raw is not None:
                self.terrain_heights = raw.flatten().astype(np.float32)
                self.initialization["init_layers_received"] += 1
                self._logger.info("Terrain heights loaded for id='%s' (%d cells)", layer_id, self.terrain_heights.size)
                return True
            self._logger.error("Could not load terrain heights from data_path=%s data_filename=%s", data_path, data_filename)
            return False

        if layer_id == config.WATER_DEPTH_LAYER_ID and config.INITIAL_STATE_SOURCE == "file":
            raw = self._load_raw_floats_from_data_path(data_path, data_filename)
            if raw is None:
                self._logger.error(
                    "Could not load water depth from data_path=%s data_filename=%s",
                    data_path, data_filename,
                )
                return False
            depths = raw.astype(np.float32)
            # Treat nodata values (negative sentinel, e.g. -9999) as dry
            depths = np.where(depths < 0, 0.0, depths)
            if depths.shape != self.grid.shape:
                resized = np.zeros(self.grid.shape, dtype=np.float32)
                h = min(depths.shape[0], self.grid.shape[0])
                w = min(depths.shape[1], self.grid.shape[1])
                resized[:h, :w] = depths[:h, :w]
                depths = resized
            self.water_depths_m = depths
            self.grid = self._water_depth_to_palette_levels(depths)
            self.has_new_data = True
            self.initialization["init_layers_received"] += 1
            self._logger.info(
                "Water depth loaded from file for id='%s' (%d cells)", layer_id, depths.size
            )
            return True

        layer = self._load_layer_from_data_path(data_path, data_filename)
        if layer is None:
            self._logger.error(
                "Could not load init layer from data_path=%s data_filename=%s",
                data_path,
                data_filename,
            )
            return False

        if layer.shape != self.grid.shape:
            self._logger.warning(
                "Init layer shape %s does not match grid %s. Resizing by crop/pad.",
                layer.shape,
                self.grid.shape,
            )
            resized = np.zeros_like(self.grid)
            h = min(layer.shape[0], self.grid.shape[0])
            w = min(layer.shape[1], self.grid.shape[1])
            resized[:h, :w] = layer[:h, :w]
            layer = resized

        self.grid = layer
        self.has_new_data = True
        self.initialization["init_layers_received"] += 1
        self._logger.info("Init layer applied for id='%s'", layer_id)
        return True

    def mark_init_agent_eof(self, event: dict):
        self.initialization["init_agent_complete"] = True
        self._logger.info("InitAgent_EOF recibido. Fin de carga de capas base.")

    def mark_init_eof(self, event: dict):
        self.initialization["init_complete"] = True
        total_chunks_sent = event.get("total_chunks_sent")
        if total_chunks_sent is not None:
            self._logger.info(
                "Initialization completed. total_chunks_sent=%s, init_layers_received=%s",
                total_chunks_sent,
                self.initialization["init_layers_received"],
            )

    def update_from_deltas(self, x_coords: list, y_coords: list, step_index: int):
        """
        Updates the grid state based on the received deltas.
        Applies XOR logic to invert the state of specific cells.
        """
        if not x_coords:
            if config.DEBUG_MODE:
                self._logger.debug(f"Frame {step_index}: No changes detected.")
            return

        cols = np.array(x_coords)
        rows = np.array(y_coords)

        # --- Validation Logic ---
        # Checks for out-of-bounds coordinates to prevent silent crashes.
        # This preserves the safety checks from the original script.
        max_y, max_x = self.grid.shape
        if np.any(cols >= max_x) or np.any(rows >= max_y):
            self._logger.error(
                f"FATAL ERROR: Coordinates out of bounds in step {step_index}. "
                f"Max X: {np.max(cols)}, Max Y: {np.max(rows)}"
            )
            return

        if np.any(cols < 0) or np.any(rows < 0):
            self._logger.error("FATAL ERROR: Negative coordinates received.")
            return

        # --- Update Logic ---
        # Applies XOR operation (dry <-> wet) using NumPy indexing.
        # grid[rows, cols] ^= 1 handles the state toggle efficiently.
        self.grid[rows, cols] ^= 1
        
        self.has_new_data = True
        
        if config.DEBUG_MODE:
            self._logger.info(f"Frame {step_index} processed. {len(cols)} cells updated.")

    def consume_data(self):
        """
        Returns the current grid and resets the 'new data' flag.
        Useful for the visualizer to know if it needs to redraw.
        """
        self.has_new_data = False
        return self.grid

    def collect_from_layer_event(self, event: dict) -> list:
        """Parse EYE_SetState_Layer and return (row, col, palette_value, water_depth_m) tuples."""
        changes = event.get("changes", {})
        cells = changes.get("cells", {})
        if not isinstance(cells, dict) or not cells:
            return []
        max_y, max_x = self.grid.shape
        result = []
        for key, cell in cells.items():
            try:
                flat_index = int(key)
            except (TypeError, ValueError):
                self._logger.warning("Celda con clave no entera ignorada: %s", key)
                continue
            row = flat_index // max_x
            col = flat_index % max_x
            if row >= max_y or col >= max_x:
                self._logger.warning("Flat index %d out of bounds (row=%d, col=%d), skipped", flat_index, row, col)
                continue
            cell_value = self._resolve_cell_value(cell)
            if cell_value is None:
                continue
            height = float(cell.get("height", 0.0)) if isinstance(cell, dict) else 0.0
            result.append((row, col, int(cell_value), height))
        return result

    def collect_from_object_event(self, event: dict) -> list:
        """Parse EYE_SetState and return a single (row, col, value) tuple without touching the grid."""
        changes = event.get("changes", {})
        coord = changes.get("coord", {})
        x = coord.get("x")
        y = coord.get("y")
        if x is None or y is None:
            self._logger.warning("EYE_SetState sin coord, ignorado")
            return []
        x, y = int(x), int(y)
        max_y, max_x = self.grid.shape
        if x < 0 or y < 0 or x >= max_x or y >= max_y:
            self._logger.error("EYE_SetState coord fuera de bounds: x=%s y=%s", x, y)
            return []
        value = self._resolve_cell_value({
            "value": changes.get("value"),
            "level": changes.get("level"),
            "state": changes.get("state"),
            "depth_level": changes.get("depth_level"),
            "risk_level": changes.get("risk_level"),
        })
        if value is None:
            value = 1
        return [(y, x, int(value))]

    def apply_bulk_changes(self, pending: list) -> bool:
        """Apply accumulated (row, col, palette_value, ...) changes to the uint8 grid."""
        if not pending:
            return False
        rows = np.array([r for r, c, *_ in pending], dtype=np.intp)
        cols = np.array([c for r, c, *_ in pending], dtype=np.intp)
        vals = np.array([v for r, c, v, *_ in pending], dtype=np.uint8)
        self.grid[rows, cols] = vals
        self.has_new_data = True
        return True

    def apply_bulk_float_changes(self, pending: list) -> None:
        """Apply accumulated (row, col, _, water_depth_m) changes to the float32 depth grid."""
        if not pending or len(pending[0]) < 4:
            return
        rows = np.array([r for r, c, v, h in pending], dtype=np.intp)
        cols = np.array([c for r, c, v, h in pending], dtype=np.intp)
        heights = np.array([h for r, c, v, h in pending], dtype=np.float32)
        self.water_depths_m[rows, cols] = heights

    def update_from_layer_event(self, event: dict) -> bool:
        """Apply layer changes from a JSON EYE_SetState_Layer event.

        Supported shape:
        {
          "changes": {
            "cells": {
              "345": {"state": "FLOODED", "height": 10.0},
              "1024": {"state": "OBSTACLE_DESTROYED", "height": 10.0}
            }
          }
        }
        """
        changes = event.get("changes", {})
        cells = changes.get("cells", {})

        if not isinstance(cells, dict) or not cells:
            return False

        rows = []
        cols = []
        values = []

        max_y, max_x = self.grid.shape
        for key, cell in cells.items():
            try:
                flat_index = int(key)
            except (TypeError, ValueError):
                self._logger.warning("Cell with non-integer key ignored: %s", key)
                continue

            row = flat_index // max_x
            col = flat_index % max_x

            cell_value = self._resolve_cell_value(cell)
            if cell_value is None:
                continue

            cols.append(col)
            rows.append(row)
            values.append(int(cell_value))

        if not rows:
            return False

        cols_arr = np.array(cols)
        rows_arr = np.array(rows)

        max_y, max_x = self.grid.shape
        if np.any(cols_arr >= max_x) or np.any(rows_arr >= max_y):
            self._logger.error(
                "Coordinates out of bounds in layer event. Max X: %s, Max Y: %s",
                int(np.max(cols_arr)),
                int(np.max(rows_arr)),
            )
            return False

        if np.any(cols_arr < 0) or np.any(rows_arr < 0):
            self._logger.error("Negative coordinates received in layer event.")
            return False

        value_arr = np.array(values, dtype=np.uint8)
        self.grid[rows_arr, cols_arr] = value_arr
        self.has_new_data = True
        return True

    def update_from_object_event(self, event: dict) -> bool:
        """Apply a single-object update from an EYE_SetState event."""
        changes = event.get("changes", {})
        coord = changes.get("coord", {})
        x = coord.get("x")
        y = coord.get("y")

        if x is None or y is None:
            self._logger.warning("EYE_SetState received without coord")
            return False

        x = int(x)
        y = int(y)
        max_y, max_x = self.grid.shape
        if x < 0 or y < 0 or x >= max_x or y >= max_y:
            self._logger.error("EYE_SetState coord out of bounds: x=%s y=%s", x, y)
            return False

        value = self._resolve_cell_value({
            "value": changes.get("value"),
            "level": changes.get("level"),
            "state": changes.get("state"),
            "depth_level": changes.get("depth_level"),
            "risk_level": changes.get("risk_level"),
        })
        if value is None:
            value = 1

        self.grid[y, x] = np.uint8(value)
        self.has_new_data = True
        return True

    def _resolve_cell_value(self, cell: dict):
        """Resolve a numeric palette value from different cell payload variants."""
        # Check for numeric values in these keys (including "state" if passed as a number)
        for numeric_key in ("value", "level", "depth_level", "risk_level", "state"):
            if numeric_key in cell:
                val = cell[numeric_key]
                if isinstance(val, (int, float)):
                    return int(val)
                if isinstance(val, str) and val.isnumeric():
                    return int(val)

        state = cell.get("state")
        if isinstance(state, str):
            return config.STATE_TO_VALUE.get(state.upper(), 1)

        return 1

    def _load_layer_from_data_path(self, data_path: str, data_filename: str):
        path_obj = Path(data_path)
        candidates = []

        if path_obj.is_absolute():
            candidates.append(path_obj)
        else:
            # Try both CWD-relative and configured data-root-relative paths.
            candidates.append(path_obj.resolve())
            candidates.append((config.DEFAULT_DATA_ROOT / path_obj).resolve())
            # Fallback: prepend data/ in case the sender omitted it
            candidates.append((config.DEFAULT_DATA_ROOT / "data" / path_obj).resolve())

        # Preserve order while removing duplicates.
        deduped_candidates = []
        seen = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            deduped_candidates.append(candidate)

        for base in deduped_candidates:
            layer = self._load_layer_candidate(base, data_filename)
            if layer is not None:
                return layer

        return None

    def _load_layer_candidate(self, base: Path, data_filename: str):
        # Accept folder paths like .../water_depth and explicit file paths.
        if base.is_dir():
            # Primary path: IDRISI (.doc + .img) through shared I/O module.
            try:
                raster = IdrisiIO.read(base, data_filename, read_metadata=True)
                return self._to_palette_levels(raster.data)
            except Exception as exc:
                self._logger.warning(
                    "Failed IDRISI read for folder=%s filename=%s: %s",
                    base,
                    data_filename,
                    exc,
                )

            # Fallbacks for tests and mixed datasets.
            img_path = base / f"{data_filename}.img"
            if img_path.exists():
                return self._load_img_as_levels(img_path)

            npy_path = base / f"{data_filename}.npy"
            if npy_path.exists():
                return self._to_palette_levels(np.load(npy_path))

            csv_path = base / f"{data_filename}.csv"
            if csv_path.exists():
                return self._to_palette_levels(np.loadtxt(csv_path, delimiter=","))

            return None

        if base.is_file():
            suffix = base.suffix.lower()
            if suffix == ".img":
                # If metadata is available, prefer IDRISI reader for shape/dtype fidelity.
                doc_file = base.with_suffix(".doc")
                if doc_file.exists():
                    try:
                        raster = IdrisiIO.read(base.parent, base.stem, read_metadata=True)
                        return self._to_palette_levels(raster.data)
                    except Exception as exc:
                        self._logger.warning("Failed IDRISI read for %s: %s", base, exc)
                return self._load_img_as_levels(base)
            if suffix == ".npy":
                return self._to_palette_levels(np.load(base))
            if suffix == ".csv":
                return self._to_palette_levels(np.loadtxt(base, delimiter=","))

        return None

    def _load_img_as_levels(self, img_file: Path):
        try:
            raw = np.loadtxt(img_file)
            return self._to_palette_levels(raw)
        except Exception as exc:
            self._logger.error("Failed to load IDRISI img file %s: %s", img_file, exc)
            return None

    def _load_raw_floats_from_data_path(self, data_path: str, data_filename: str) -> np.ndarray | None:
        """Load a layer as raw float32 values without palette conversion."""
        path_obj = Path(data_path)
        candidates = [path_obj] if path_obj.is_absolute() else [
            path_obj.resolve(),
            (config.DEFAULT_DATA_ROOT / path_obj).resolve(),
            (config.DEFAULT_DATA_ROOT / "data" / path_obj).resolve(),
        ]
        seen: set[str] = set()
        for base in candidates:
            key = str(base)
            if key in seen:
                continue
            seen.add(key)
            raw = self._load_raw_candidate(base, data_filename)
            if raw is not None:
                return raw
        return None

    def _load_raw_candidate(self, base: Path, data_filename: str) -> np.ndarray | None:
        if base.is_dir():
            try:
                raster = IdrisiIO.read(base, data_filename, read_metadata=True)
                return np.array(raster.data, dtype=np.float32)
            except Exception:
                pass
            for suffix, loader in [(".npy", np.load), (".csv", lambda p: np.loadtxt(p, delimiter=","))]:
                path = base / f"{data_filename}{suffix}"
                if path.exists():
                    try:
                        return np.array(loader(path), dtype=np.float32)
                    except Exception:
                        pass
        elif base.is_file():
            try:
                if base.suffix.lower() == ".npy":
                    return np.array(np.load(base), dtype=np.float32)
                if base.suffix.lower() == ".csv":
                    return np.array(np.loadtxt(base, delimiter=","), dtype=np.float32)
            except Exception:
                pass
        return None

    def _water_depth_to_palette_levels(self, depths: np.ndarray) -> np.ndarray:
        """Map float water-depth values to palette indices using configured flood thresholds."""
        levels = np.zeros(depths.shape, dtype=np.uint8)
        for level_idx, threshold in sorted(config.FLOOD_LEVELS.items()):
            levels[depths >= threshold] = np.uint8(level_idx)
        return levels

    def _to_palette_levels(self, raw):
        arr = np.array(raw, dtype=float)
        max_level = max(1, int(config.PALETTE_MAX_VALUE))

        finite_mask = np.isfinite(arr)
        if not np.any(finite_mask):
            return np.zeros_like(arr, dtype=np.uint8)

        finite_values = arr[finite_mask]
        min_val = float(np.min(finite_values))
        max_val = float(np.max(finite_values))

        # Fast path when values already look like palette indices.
        if min_val >= 0.0 and max_val <= max_level and np.all(np.mod(finite_values, 1) == 0):
            return arr.astype(np.uint8)

        scaled = np.zeros_like(arr, dtype=float)
        if max_val > min_val:
            scaled[finite_mask] = (arr[finite_mask] - min_val) / (max_val - min_val)
        scaled = np.clip(scaled, 0.0, 1.0)
        levels = np.rint(scaled * max_level).astype(np.uint8)
        return levels
