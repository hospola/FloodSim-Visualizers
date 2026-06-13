import json
import logging
import queue

import paho.mqtt.client as mqtt

from . import config
from .ports import SimulationEventHandler


class MQTTMonitorClient:
    """Handle MQTT connections and route incoming JSON events to a handler.

    The internal queue is an implementation detail: paho fires _on_message
    from its own network thread, so the queue bridges that thread to the
    main thread's run() loop.  The handler (SimulationApp) never sees the
    queue.
    """

    def __init__(self, handler: SimulationEventHandler) -> None:
        self._handler = handler
        self._queue: queue.Queue = queue.Queue()
        self._logger = logging.getLogger(__name__)

        self.client = mqtt.Client(client_id=config.CLIENT_ID, clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # LWT for unexpected visualizer shutdowns.
        lwt_payload = json.dumps(
            {
                "process": "System_Disconnected",
                "source": "Visualizer_Python_X3D",
                "scenario": config.SCENARIO_NAME,
                "timestamp_utc": config.utc_now_iso(),
            }
        )
        self.client.will_set(
            config.TOPIC_SYSTEM, payload=lwt_payload, qos=config.QOS_HANDSHAKE, retain=True
        )

    def connect(self):
        try:
            self.client.connect(config.BROKER_ADDRESS, config.BROKER_PORT, config.KEEPALIVE_SECONDS)
            self.client.loop_start()
            self._logger.info(
                "Connecting to broker at %s:%s for scenario '%s'...",
                config.BROKER_ADDRESS,
                config.BROKER_PORT,
                config.SCENARIO_NAME,
            )
        except Exception as exc:
            self._logger.critical("Failed to connect to MQTT broker: %s", exc)
            raise

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        self._logger.info("Disconnected from MQTT broker.")

    def publish_ping(self):
        payload = {
            "process": "System_Ping",
            "source": "Visualizer_Python_X3D",
            "scenario": config.SCENARIO_NAME,
            "timestamp_utc": config.utc_now_iso(),
        }
        self.client.publish(
            config.TOPIC_HANDSHAKE_PING, payload=json.dumps(payload), qos=config.QOS_HANDSHAKE
        )
        self._logger.info("Published System_Ping to %s", config.TOPIC_HANDSHAKE_PING)

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self._logger.error("Connection failed with code: %s", rc)
            return

        self._logger.info("Successfully connected to broker.")
        client.subscribe(config.TOPIC_EVENTS, qos=config.QOS_EVENTS)
        client.subscribe(config.TOPIC_HANDSHAKE_PING, qos=config.QOS_HANDSHAKE)

        self._logger.info("Subscribed to events topic: %s", config.TOPIC_EVENTS)
        self._logger.info("Subscribed to handshake ping topic: %s", config.TOPIC_HANDSHAKE_PING)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:
            self._logger.error("Invalid JSON payload on topic %s: %s", msg.topic, exc)
            return

        process = payload.get("process")

        if msg.topic == config.TOPIC_HANDSHAKE_PING and process == "System_Ping":
            self._reply_pong()
            return

        # Queue non-handshake payloads for the main-thread run() loop.
        self._queue.put({"topic": msg.topic, "payload": payload})

    def run(self) -> None:
        """Main event loop: drain the internal queue and delegate to the handler."""
        running = True
        while running:
            try:
                item = self._queue.get(timeout=config.IDLE_SLEEP_SECONDS)
                payload = item.get("payload", {})
                self._handler.handle_event(payload)
                self._queue.task_done()
                if payload.get("process") == "Sim_End":
                    running = False
            except queue.Empty:
                self._handler.on_idle()

    def publish_chunk_ack(self):
        payload = json.dumps({"process": "ChunkAck"})
        self.client.publish(
            config.TOPIC_CONTROL_EVENTS, payload=payload, qos=config.QOS_EVENTS
        )
        self._logger.debug("Published ChunkAck to %s", config.TOPIC_CONTROL_EVENTS)

    def _reply_pong(self):
        payload = {
            "process": "System_Pong",
            "source": "Visualizer_Python_X3D",
            "scenario": config.SCENARIO_NAME,
            "timestamp_utc": config.utc_now_iso(),
        }
        self.client.publish(
            config.TOPIC_HANDSHAKE_PONG, payload=json.dumps(payload), qos=config.QOS_HANDSHAKE
        )
        self._logger.info("Published System_Pong to %s", config.TOPIC_HANDSHAKE_PONG)
