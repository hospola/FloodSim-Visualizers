import logging
import os
import sys

from . import config
from .network import MQTTMonitorClient
from .renderers.registry import create_renderer, create_depth_provider
from .simulation_app import SimulationApp


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
)


def main() -> None:
    output_folder = os.getenv("DANASIM_OUTPUT_FOLDER", "sim_outputs")
    renderer = create_renderer(config.RENDERER_TYPE, output_folder)
    depth_provider = create_depth_provider(config.DEPTH_PROVIDER_TYPE)

    # SimulationApp needs a ControlPublisher and MQTTMonitorClient needs the
    # app as its handler — a simple proxy breaks the circular construction dep.
    class _ControlProxy:
        _real = None
        def publish_chunk_ack(self) -> None:
            assert self._real is not None, (
                "_ControlProxy not wired — assign proxy._real = client before calling run()"
            )
            self._real.publish_chunk_ack()

    proxy = _ControlProxy()
    app = SimulationApp(renderer, depth_provider, proxy)
    client = MQTTMonitorClient(app)
    proxy._real = client

    print(f"Monitor iniciado para escenario '{config.SCENARIO_NAME}'. Esperando mensajes...")

    try:
        client.connect()
        client.run()
    except KeyboardInterrupt:
        print("\nInterromput per l'usuari.")
    finally:
        app.close()
        client.disconnect()
        print("Clean exit.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
