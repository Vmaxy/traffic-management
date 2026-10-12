"""Background-threaded, non-blocking Arduino phase sender and ACK reader."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from traffic_core.safety_fsm import Phase


LOGGER = logging.getLogger(__name__)
ARDUINO_WATCHDOG_SECONDS = 3.0

PHASE_COMMANDS = {
    Phase.ALL_RED: "ALL_R\n",
    Phase.NS_GREEN: "NS_G\n",
    Phase.NS_YELLOW: "NS_Y\n",
    Phase.EW_GREEN: "EW_G\n",
    Phase.EW_YELLOW: "EW_Y\n",
}


class ArduinoController:
    def __init__(
        self,
        port: str | None = None,
        baud_rate: int = 9600,
        heartbeat_seconds: float = 1.0,
        reconnect_seconds: float = 2.0,
        serial_factory: Callable[..., object] | None = None,
    ) -> None:
        if baud_rate <= 0 or heartbeat_seconds <= 0 or reconnect_seconds <= 0:
            raise ValueError("baud rate and serial intervals must be greater than zero")
        if heartbeat_seconds >= ARDUINO_WATCHDOG_SECONDS:
            raise ValueError(
                "heartbeat_seconds must be less than the Arduino's "
                f"{ARDUINO_WATCHDOG_SECONDS:g}-second watchdog"
            )
        self.port = port
        self.baud_rate = baud_rate
        self.heartbeat_seconds = heartbeat_seconds
        self.reconnect_seconds = reconnect_seconds
        self._serial_factory = serial_factory
        self._desired_phase = Phase.ALL_RED
        self._desired_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._force_reconnect = threading.Event()
        self._all_red_attempted = threading.Event()
        self._status_lock = threading.Lock()
        self._ack_lock = threading.Lock()
        self._acknowledgments: list[str] = []
        self._receive_buffer = bytearray()
        self._connected = False
        self._warned_unavailable = False
        self._thread = threading.Thread(target=self._run, name="arduino-serial", daemon=True)
        self._thread.start()

    @property
    def status(self) -> str:
        with self._status_lock:
            return "CONNECTED" if self._connected else "SIMULATION (not connected)"

    def pop_acknowledgments(self) -> list[str]:
        """Return received ACK/error lines without waiting for serial I/O."""
        with self._ack_lock:
            acknowledgments, self._acknowledgments = self._acknowledgments, []
        return acknowledgments

    def set_phase(self, phase: Phase | str) -> None:
        try:
            requested = phase if isinstance(phase, Phase) else Phase(phase)
        except ValueError as exc:
            raise ValueError(f"Unknown traffic phase: {phase!r}") from exc
        with self._desired_lock:
            changed = requested is not self._desired_phase
            self._desired_phase = requested
        if changed:
            self._wake.set()

    def shutdown(self, timeout: float = 1.0) -> None:
        self._all_red_attempted.clear()
        self.set_phase(Phase.ALL_RED)
        self._force_reconnect.set()
        self._wake.set()
        delivered = self._all_red_attempted.wait(timeout=max(timeout, 0.0))
        if not delivered:
            LOGGER.warning("Could not confirm an all-red serial command before shutdown")
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            LOGGER.warning("Serial worker did not stop within %.1f seconds", timeout)

    def _create_serial(self) -> object | None:
        try:
            if self._serial_factory is not None:
                return self._serial_factory(
                    port=self.port,
                    baudrate=self.baud_rate,
                    timeout=0,
                    write_timeout=0,
                )

            import serial
            from serial.tools import list_ports

            port = self.port
            if port is None:
                recognized = ("arduino", "usb serial", "ch340", "cp210", "ftdi")
                candidates = [
                    item.device
                    for item in list_ports.comports()
                    if any(token in f"{item.description} {item.manufacturer}".lower() for token in recognized)
                ]
                if len(candidates) == 1:
                    port = candidates[0]
                    LOGGER.info("Auto-detected Arduino-compatible serial port %s", port)
                elif len(candidates) > 1:
                    LOGGER.debug("Multiple Arduino-compatible ports found (%s)", ", ".join(candidates))
                    return None
                else:
                    return None
            return serial.Serial(port=port, baudrate=self.baud_rate, timeout=0, write_timeout=0)
        except ImportError:
            LOGGER.debug("pyserial is unavailable")
        except (OSError, ValueError) as exc:
            LOGGER.debug("Unable to connect to Arduino serial port: %s", exc)
        return None

    def _read_feedback(self, connection: object) -> None:
        """Drain only bytes already buffered by pyserial; never wait for a line."""
        available = int(getattr(connection, "in_waiting", 0))
        if available <= 0:
            return
        data = connection.read(available)
        if not data:
            return
        self._receive_buffer.extend(data)
        while b"\n" in self._receive_buffer:
            line, _, remainder = self._receive_buffer.partition(b"\n")
            self._receive_buffer = bytearray(remainder)
            decoded = line.decode("utf-8", errors="replace").strip("\r ")
            if decoded:
                with self._ack_lock:
                    self._acknowledgments.append(decoded)

    def _run(self) -> None:
        connection: object | None = None
        last_attempt = 0.0
        last_sent_phase: Phase | None = None
        last_sent_at = 0.0
        last_simulated_phase: Phase | None = None

        while not self._stop.is_set():
            self._wake.wait(timeout=0.05)
            self._wake.clear()
            if self._stop.is_set():
                break

            if connection is not None:
                try:
                    self._read_feedback(connection)
                except (OSError, ValueError, AttributeError) as exc:
                    LOGGER.warning("Arduino serial read failed; reconnecting: %s", exc)
                    self._close_connection(connection)
                    connection = None
                    self._set_connected(False)
                    last_attempt = time.monotonic()
                    last_sent_phase = None
                    continue

            with self._desired_lock:
                desired = self._desired_phase
            now = time.monotonic()
            if desired is last_sent_phase and now - last_sent_at < self.heartbeat_seconds:
                if desired is Phase.ALL_RED and self._force_reconnect.is_set():
                    self._all_red_attempted.set()
                continue

            if connection is None and (
                now - last_attempt >= self.reconnect_seconds or self._force_reconnect.is_set()
            ):
                last_attempt = now
                connection = self._create_serial()
                self._set_connected(connection is not None)
                if connection is None:
                    if not self._warned_unavailable:
                        LOGGER.warning(
                            "Arduino unavailable; using simulation mode. Set TRAFFIC_SERIAL_PORT if auto-detection failed."
                        )
                        self._warned_unavailable = True
                    if desired is not last_simulated_phase:
                        LOGGER.info("SIMULATION: %s", PHASE_COMMANDS[desired].strip())
                        last_simulated_phase = desired
                else:
                    self._warned_unavailable = False
                    self._receive_buffer.clear()
                if connection is None and desired is Phase.ALL_RED and self._force_reconnect.is_set():
                    self._all_red_attempted.set()

            if connection is None:
                continue

            try:
                payload = PHASE_COMMANDS[desired].encode("utf-8")
                written = connection.write(payload)
                if written != len(payload):
                    raise OSError(f"short serial write ({written} bytes)")
                connection.flush()
            except (OSError, ValueError, AttributeError) as exc:
                LOGGER.warning("Arduino serial write failed; switching to simulation mode: %s", exc)
                self._close_connection(connection)
                connection = None
                self._set_connected(False)
                last_attempt = time.monotonic()
                last_sent_phase = None
                continue

            LOGGER.debug("Sent phase %s to Arduino", desired.value)
            last_sent_phase = desired
            last_sent_at = time.monotonic()
            last_simulated_phase = None
            if desired is Phase.ALL_RED and self._force_reconnect.is_set():
                self._all_red_attempted.set()

        if connection is not None:
            self._close_connection(connection)
        self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        with self._status_lock:
            previous = self._connected
            self._connected = connected
        if previous != connected:
            if connected:
                LOGGER.info("Arduino serial link connected")
            elif self._stop.is_set():
                LOGGER.info("Arduino serial link closed")
            else:
                LOGGER.warning("Arduino serial link disconnected")

    @staticmethod
    def _close_connection(connection: object) -> None:
        try:
            connection.close()
        except (OSError, AttributeError):
            LOGGER.debug("Serial connection was already closed", exc_info=True)


ArduinoSerialController = ArduinoController
