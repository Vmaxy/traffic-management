import pytest

from traffic_core.safety_fsm import Phase, SafetyFSM


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


def test_green_target_is_latched_through_clearance(clock):
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
    assert fsm.tick() is Phase.EW_GREEN


def test_only_green_phases_can_be_requested(clock):
    fsm = SafetyFSM(clock=clock)
    with pytest.raises(ValueError, match="Demand requests"):
        fsm.request_phase(Phase.NS_YELLOW)


@pytest.mark.parametrize("duration", [0, -1])
def test_rejects_invalid_clearance_durations(duration):
    with pytest.raises(ValueError, match="greater than zero"):
        SafetyFSM(min_green_seconds=duration)


@pytest.mark.parametrize("duration", [float("nan"), float("inf")])
def test_rejects_non_finite_durations(duration):
    with pytest.raises(ValueError, match="greater than zero"):
        SafetyFSM(yellow_seconds=duration)


def test_rejects_time_going_backwards(clock):
    fsm = SafetyFSM(clock=clock)
    clock.advance(1.0)
    assert fsm.tick() is Phase.ALL_RED
    with pytest.raises(ValueError, match="monotonic"):
        fsm.tick(now=0.5)


def test_never_enters_both_conflicting_green_phases(clock):
    fsm = SafetyFSM(1.0, 0.5, 0.25, clock=clock)
    fsm.request_phase(Phase.NS_GREEN)
    previous_phase = fsm.phase
    for _ in range(4):
        current_phase = fsm.tick()
        assert not (
            previous_phase is Phase.NS_GREEN and current_phase is Phase.EW_GREEN
        )
        assert not (
            previous_phase is Phase.EW_GREEN and current_phase is Phase.NS_GREEN
        )
        previous_phase = current_phase
        clock.advance(0.5)

    fsm.request_phase(Phase.EW_GREEN)
    for _ in range(12):
        current_phase = fsm.tick()
        assert not (
            previous_phase is Phase.NS_GREEN and current_phase is Phase.EW_GREEN
        )
        assert not (
            previous_phase is Phase.EW_GREEN and current_phase is Phase.NS_GREEN
        )
        previous_phase = current_phase
        clock.advance(0.5)


def test_green_phase_ends_after_its_latched_duration(clock):
    fsm = SafetyFSM(1.0, 0.5, 0.25, clock=clock)
    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(0.25)
    assert fsm.tick() is Phase.NS_GREEN
    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(5.0)
    assert fsm.tick() is Phase.NS_YELLOW


def test_green_duration_is_clamped_and_latched_when_phase_starts(clock):
    fsm = SafetyFSM(
        min_green_seconds=2.0,
        max_green_seconds=8.0,
        yellow_seconds=1.0,
        all_red_seconds=0.5,
        clock=clock,
    )
    fsm.request_phase(Phase.NS_GREEN, green_seconds=50.0)
    clock.advance(0.5)
    assert fsm.tick() is Phase.NS_GREEN
    fsm.request_phase(Phase.EW_GREEN, green_seconds=4.0)
    clock.advance(7.99)
    assert fsm.tick() is Phase.NS_GREEN
    clock.advance(0.01)
    assert fsm.tick() is Phase.NS_YELLOW
    fsm.request_phase(Phase.NS_GREEN, green_seconds=2.0)
    clock.advance(1.0)
    assert fsm.tick() is Phase.ALL_RED
    clock.advance(0.5)
    assert fsm.tick() is Phase.EW_GREEN


def test_emergency_request_switches_at_minimum_green_not_before(clock):
    fsm = SafetyFSM(3.0, 0.5, 0.25, clock=clock)
    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(0.25)
    assert fsm.tick() is Phase.NS_GREEN

    fsm.request_phase(Phase.EW_GREEN, emergency=True)
    clock.advance(2.99)
    assert fsm.tick() is Phase.NS_GREEN
    clock.advance(0.01)
    assert fsm.tick() is Phase.NS_YELLOW


def test_max_green_forces_and_retains_opposing_phase_through_clearance(clock):
    fsm = SafetyFSM(1.0, 0.5, 0.25, clock=clock, max_green_seconds=2.0)
    fsm.request_phase(
        Phase.NS_GREEN,
        green_seconds=2.0,
        opposing_green_seconds=1.5,
    )
    clock.advance(0.25)
    assert fsm.tick() is Phase.NS_GREEN

    clock.advance(2.0)
    assert fsm.tick() is Phase.NS_YELLOW
    fsm.request_phase(Phase.NS_GREEN)  # Equal demand must not cancel the forced handoff.
    clock.advance(0.5)
    assert fsm.tick() is Phase.ALL_RED
    fsm.request_phase(Phase.NS_GREEN)
    clock.advance(0.25)
    assert fsm.tick() is Phase.EW_GREEN
    clock.advance(1.49)
    assert fsm.tick() is Phase.EW_GREEN
    clock.advance(0.01)
    assert fsm.tick() is Phase.EW_YELLOW
