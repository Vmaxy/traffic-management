from __future__ import annotations

import threading
import time

import pytest

from traffic_core.safety_fsm import Phase
from traffic_core.serial_controller import ArduinoSerialController, PHASE_COMMANDS


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.write_event = threading.Event()
        self.closed = False
        self.lock = threading.Lock()

    def write(self, data: bytes) -> int:
        with self.lock:
            self.writes.append(data)
        self.write_event.set()
        return len(data)

    def close(self) -> None:
        self.closed = True

    def count(self, command: bytes) -> int:
        with self.lock:
            return self.writes.count(command)


def wait_until(predicate, timeout: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_sends_phases_and_periodic_keepalives():
    fake_serial = FakeSerial()
    controller = ArduinoSerialController(
        port="fake",
        heartbeat_seconds=0.05,
        reconnect_seconds=0.05,
        serial_factory=lambda **_: fake_serial,
    )
    try:
        assert wait_until(lambda: fake_serial.count(PHASE_COMMANDS[Phase.ALL_RED].encode()) >= 1)
        controller.set_phase(Phase.NS_GREEN)
        green_command = PHASE_COMMANDS[Phase.NS_GREEN].encode()
        assert wait_until(lambda: fake_serial.count(green_command) >= 2)
        assert controller.status == "CONNECTED"
    finally:
        controller.shutdown()

    assert fake_serial.closed
    assert fake_serial.count(PHASE_COMMANDS[Phase.ALL_RED].encode()) >= 2


def test_phase_update_is_non_blocking_when_serial_open_is_slow():
    opening = threading.Event()
    factory_entered = threading.Event()
    fake_serial = FakeSerial()

    def slow_factory(**_):
        factory_entered.set()
        opening.wait(timeout=1.0)
        return fake_serial

    controller = ArduinoSerialController(
        port="fake",
        reconnect_seconds=0.05,
        serial_factory=slow_factory,
    )
    try:
        assert factory_entered.wait(timeout=1.0)
        started = time.monotonic()
        controller.set_phase(Phase.EW_GREEN)
        update_duration = time.monotonic() - started
        assert update_duration < 0.1
        opening.set()
        assert wait_until(lambda: fake_serial.count(PHASE_COMMANDS[Phase.EW_GREEN].encode()) >= 1)
    finally:
        opening.set()
        controller.shutdown()


@pytest.mark.parametrize("heartbeat", [2.5, 3.0])
def test_heartbeat_must_precede_hardware_watchdog(heartbeat):
    with pytest.raises(ValueError, match="2.5-second watchdog"):
        ArduinoSerialController(heartbeat_seconds=heartbeat)
