from __future__ import annotations

import threading
import time

import pytest

from traffic_core.safety_fsm import Phase
from traffic_core.serial_controller import ArduinoSerialController, LANES


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.write_event = threading.Event()
        self.closed = False
        self.lock = threading.Lock()
        self.incoming = bytearray()

    def write(self, data: bytes) -> int:
        with self.lock:
            self.writes.append(data)
        self.write_event.set()
        return len(data)

    def close(self) -> None:
        self.closed = True

    def flush(self) -> None:
        pass

    @property
    def in_waiting(self) -> int:
        with self.lock:
            return len(self.incoming)

    def read(self, size: int) -> bytes:
        with self.lock:
            result = bytes(self.incoming[:size])
            del self.incoming[:size]
            return result

    def send_feedback(self, data: bytes) -> None:
        with self.lock:
            self.incoming.extend(data)

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
        controller.set_plan(Phase.NS_GREEN, {lane: 5.0 for lane in LANES})
        assert wait_until(lambda: fake_serial.count(b"SET:N:5.00\n") >= 1)
        assert wait_until(lambda: fake_serial.count(b"NEXT:NS\n") >= 2)
        assert controller.status == "CONNECTED"
    finally:
        controller.shutdown()

    assert fake_serial.closed
    assert fake_serial.count(b"SAFE:RED\n") >= 1


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
        controller.set_plan(Phase.EW_GREEN, {lane: 6.0 for lane in LANES})
        update_duration = time.monotonic() - started
        assert update_duration < 0.1
        opening.set()
        assert wait_until(lambda: fake_serial.count(b"NEXT:EW\n") >= 1)
    finally:
        opening.set()
        controller.shutdown()


def test_reads_newline_framed_acknowledgments_without_blocking():
    fake_serial = FakeSerial()
    controller = ArduinoSerialController(
        port="fake",
        heartbeat_seconds=0.1,
        reconnect_seconds=0.05,
        serial_factory=lambda **_: fake_serial,
    )
    try:
        assert wait_until(lambda: controller.status == "CONNECTED")
        fake_serial.send_feedback(b"ACK:NS_G\r\n")
        assert wait_until(lambda: controller.pop_acknowledgments() == ["ACK:NS_G"])
    finally:
        controller.shutdown()


def test_plan_uses_one_duration_command_per_lane_and_a_direction_request():
    assert LANES == ("NORTH", "SOUTH", "EAST", "WEST")
    expected = (
        b"SET:N:3.00\n",
        b"SET:S:4.00\n",
        b"SET:E:5.00\n",
        b"SET:W:6.00\n",
        b"NEXT:EW\n",
    )
    fake_serial = FakeSerial()
    controller = ArduinoSerialController(
        port="fake",
        reconnect_seconds=0.05,
        serial_factory=lambda **_: fake_serial,
    )
    try:
        controller.set_plan(
            Phase.EW_GREEN,
            {"NORTH": 3, "SOUTH": 4, "EAST": 5, "WEST": 6},
        )
        assert wait_until(lambda: all(fake_serial.count(command) >= 1 for command in expected))
    finally:
        controller.shutdown()


@pytest.mark.parametrize("heartbeat", [10.0, 11.0])
def test_heartbeat_must_precede_hardware_watchdog(heartbeat):
    with pytest.raises(ValueError, match="10-second watchdog"):
        ArduinoSerialController(heartbeat_seconds=heartbeat)
