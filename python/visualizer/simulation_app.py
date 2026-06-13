from __future__ import annotations

import logging
import time

from . import config
from .data_model import SimulationGrid
from .depth_providers.base import DepthProvider
from .palette import resolve_palette
from .ports import ControlPublisher
from .renderers.base import BaseRenderer, FrameData, GridMeta


class SimulationApp:
    """Application core: owns simulation state and dispatches MQTT events.

    Depends only on ports (BaseRenderer, DepthProvider, ControlPublisher),
    never on concrete adapters.  Satisfies SimulationEventHandler structurally.
    """

    def __init__(
        self,
        renderer: BaseRenderer,
        depth_provider: DepthProvider,
        control: ControlPublisher,
    ) -> None:
        self._simulation = SimulationGrid()
        self._renderer = renderer
        self._depth_provider = depth_provider
        self._control = control
        self._pending_changes: list = []
        self._chunks_per_batch: int = 0
        self._chunks_since_ack: int = 0
        self._step_index: int = 0
        self._frame_start_time: float | None = None
        self._running: bool = True
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # SimulationEventHandler protocol
    # ------------------------------------------------------------------

    def handle_event(self, event: dict) -> None:
        process = event.get("process")

        if process == "InitMap_Config":
            ok = self._simulation.apply_init_map_config(event)
            if ok:
                rows, cols = self._simulation.grid.shape
                self._depth_provider.setup(rows, cols)
                self._logger.info("InitMap_Config aplicado. Grid %sx%s", cols, rows)
            else:
                self._logger.error("InitMap_Config inválido")

        elif process == "InitAgent_Layer":
            ok = self._simulation.apply_init_agent_layer(event)
            if ok:
                self._logger.info(
                    "InitAgent_Layer aplicado. Capas init recibidas: %s",
                    self._simulation.initialization["init_layers_received"],
                )
            else:
                self._logger.error("No se pudo aplicar InitAgent_Layer")

        elif process == "InitAgent_EOF":
            self._simulation.mark_init_agent_eof(event)
            if config.INITIAL_STATE_SOURCE == "file":
                self._load_water_depth_from_file()

        elif process == "Init_EOF":
            self._simulation.mark_init_eof(event)
            meta = GridMeta(
                rows=self._simulation.grid.shape[0],
                cols=self._simulation.grid.shape[1],
                cell_size_m=self._simulation.cell_size_m,
                terrain_heights=self._simulation.terrain_heights,
                palette=resolve_palette(self._simulation.color_palette, config.COLOR_PALETTE_FILE),
            )
            self._renderer.setup(meta)
            if config.RENDER_ON_INIT_EOF:
                self._renderer.save_snapshot(self._build_frame(), self._step_index)
                self._step_index += 1
                self._simulation.consume_data()
                print("Inicializacion completada. Snapshot inicial guardado.")

        elif process == "FrameStart":
            self._pending_changes.clear()
            self._chunks_per_batch = event.get("chunks_per_batch", 0)
            self._chunks_since_ack = 0
            self._frame_start_time = time.monotonic()
            self._logger.info(
                "FrameStart: total_chunks=%d, chunks_per_batch=%d",
                event.get("total_chunks", 0),
                self._chunks_per_batch,
            )

        elif process == "FrameEnd":
            n = len(self._pending_changes)
            self._simulation.apply_bulk_changes(self._pending_changes)
            self._simulation.apply_bulk_float_changes(self._pending_changes)
            self._depth_provider.update_from_grid(self._simulation.water_depths_m)
            self._pending_changes.clear()
            self._frame_start_time = None
            self._logger.info("FrameEnd: %d cambios aplicados al grid.", n)

        elif process == "EYE_SetState_Layer":
            if (
                config.INITIAL_STATE_SOURCE == "file"
                and not self._simulation.initialization["init_complete"]
            ):
                self._logger.debug("EYE_SetState_Layer ignorado en modo file antes de Init_EOF")
                return
            self._pending_changes.extend(
                self._simulation.collect_from_layer_event(event)
            )
            self._maybe_publish_ack()

        elif process == "EYE_SetState":
            if (
                config.INITIAL_STATE_SOURCE == "file"
                and not self._simulation.initialization["init_complete"]
            ):
                self._logger.debug("EYE_SetState ignorado en modo file antes de Init_EOF")
                return
            self._pending_changes.extend(
                self._simulation.collect_from_object_event(event)
            )
            self._maybe_publish_ack()

        elif process == "EYE_Frame_Sync":
            self._render()
            self._logger.info(
                "EYE_Frame_Sync: snapshot guardado. simulation_time=%s",
                event.get("simulation_time"),
            )

        elif process == "Sim_End":
            self._logger.info("Sim_End recibido. Cerrando.")
            self._running = False

        elif process == "System_Disconnected":
            self._logger.info("Evento recibido: %s", process)

        else:
            self._logger.debug("Evento ignorado: %s", process)

    def on_idle(self) -> None:
        if (
            self._frame_start_time is not None
            and time.monotonic() - self._frame_start_time > config.FRAME_TIMEOUT_SECONDS
        ):
            self._logger.warning(
                "Frame timeout (%.0fs): FrameEnd not received after FrameStart. "
                "Discarding %d pending changes.",
                config.FRAME_TIMEOUT_SECONDS,
                len(self._pending_changes),
            )
            self._pending_changes.clear()
            self._frame_start_time = None
            self._chunks_per_batch = 0
            self._chunks_since_ack = 0

    def close(self) -> None:
        self._renderer.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_frame(self) -> FrameData:
        water_depths = self._depth_provider.get_water_depths(self._simulation.grid)
        return FrameData(palette_grid=self._simulation.grid, water_depths=water_depths)

    def _render(self) -> None:
        if not self._simulation.initialization["init_complete"]:
            return
        if not self._simulation.has_new_data:
            return
        self._renderer.save_snapshot(self._build_frame(), self._step_index)
        self._step_index += 1
        self._simulation.consume_data()

    def _maybe_publish_ack(self) -> None:
        if self._chunks_per_batch <= 0:
            return
        self._chunks_since_ack += 1
        if self._chunks_since_ack >= self._chunks_per_batch:
            self._control.publish_chunk_ack()
            self._chunks_since_ack = 0

    def _load_water_depth_from_file(self) -> None:
        if config.WATER_DEPTH_DATA_PATH is None:
            self._logger.error(
                "Modo file activo pero WATER_DEPTH_DATA_PATH no está configurado "
                "(comprueba que sim_config apunta a un yaml con input.file.dataset_name)"
            )
            return
        ok = self._simulation.apply_init_agent_layer({
            "id": config.WATER_DEPTH_LAYER_ID,
            "data_path": config.WATER_DEPTH_DATA_PATH,
            "data_filename": config.WATER_DEPTH_DATA_FILENAME,
        })
        if ok:
            self._logger.info(
                "Estado inicial de inundación cargado desde fichero: %s",
                config.WATER_DEPTH_DATA_PATH,
            )
        else:
            self._logger.error(
                "No se pudo cargar el estado inicial desde fichero: %s",
                config.WATER_DEPTH_DATA_PATH,
            )
