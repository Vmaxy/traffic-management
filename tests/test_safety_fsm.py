import pytest

from traffic_core.safety_fsm import Phase, SafetyFSM


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


def test_starts_all_red_then_enters_requested_green_after_clearance(clock):
    fsm = SafetyFSM(4.0, 2.0, 1.0, clock=clock)
    fsm.request_phase(Phase.NS_GREEN)

    clock.advance(0.99)
    assert fsm.tick() is Phase.ALL_RED
    clock.advance(0.01)
    assert fsm.tick() is Phase.NS_GREEN


def test_switches_ns_to_ew_only_after_minimum_green_yellow_and_all_red(clock):
    fsm = SafetyFSM(4.0, 2.0, 1.0, clock=clock)
    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(1.0)
    assert fsm.tick() is Phase.NS_GREEN

    fsm.request_phase(Phase.EW_GREEN)
    clock.advance(3.99)
    assert fsm.tick() is Phase.NS_GREEN
    clock.advance(0.01)
    assert fsm.tick() is Phase.NS_YELLOW

    clock.advance(1.99)
    assert fsm.tick() is Phase.NS_YELLOW
    clock.advance(0.01)
    assert fsm.tick() is Phase.ALL_RED

    clock.advance(0.99)
    assert fsm.tick() is Phase.ALL_RED
    clock.advance(0.01)
    assert fsm.tick() is Phase.EW_GREEN


def test_switches_ew_to_ns_through_ew_yellow_and_all_red(clock):
    fsm = SafetyFSM(1.0, 0.5, 0.25, clock=clock)
    fsm.request_phase(Phase.EW_GREEN)
    clock.advance(0.25)
    assert fsm.tick() is Phase.EW_GREEN

    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(1.0)
    assert fsm.tick() is Phase.EW_YELLOW
    clock.advance(0.5)
    assert fsm.tick() is Phase.ALL_RED
    clock.advance(0.25)
    assert fsm.tick() is Phase.NS_GREEN


def test_green_demand_cannot_bypass_clearance_once_yellow_begins(clock):
    fsm = SafetyFSM(1.0, 0.5, 0.25, clock=clock)
    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(0.25)
    assert fsm.tick() is Phase.NS_GREEN
    fsm.request_phase(Phase.EW_GREEN)
    clock.advance(1.0)
    assert fsm.tick() is Phase.NS_YELLOW

    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(0.5)
    assert fsm.tick() is Phase.ALL_RED
    clock.advance(0.25)
    assert fsm.tick() is Phase.NS_GREEN


def test_only_green_phases_can_be_requested(clock):
    fsm = SafetyFSM(clock=clock)
    with pytest.raises(ValueError, match="Demand requests"):
        fsm.request_phase(Phase.NS_YELLOW)


@pytest.mark.parametrize("duration", [0, -1])
def test_rejects_invalid_clearance_durations(duration):
    with pytest.raises(ValueError, match="greater than zero"):
        SafetyFSM(min_green_seconds=duration)
