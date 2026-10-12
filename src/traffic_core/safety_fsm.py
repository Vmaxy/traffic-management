"""Timed, conflict-safe signal phase state machine."""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable


class Phase(str, Enum):
    NS_GREEN = "NS_GREEN"
    NS_YELLOW = "NS_YELLOW"
    ALL_RED = "ALL_RED"
    EW_GREEN = "EW_GREEN"
    EW_YELLOW = "EW_YELLOW"


class SafetyFSM:
    def __init__(
        self,
        min_green_seconds: float = 4.0,
        yellow_seconds: float = 2.0,
        all_red_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_green_seconds <= 0 or yellow_seconds <= 0 or all_red_seconds <= 0:
            raise ValueError("all FSM timing intervals must be greater than zero")
        self.min_green_seconds = min_green_seconds
        self.yellow_seconds = yellow_seconds
        self.all_red_seconds = all_red_seconds
        self._clock = clock
        self.phase = Phase.ALL_RED
        self._phase_started_at = clock()
        self._requested_green: Phase | None = None

    def request_phase(self, phase: Phase | str) -> None:
        try:
            requested = phase if isinstance(phase, Phase) else Phase(phase)
        except ValueError as exc:
            raise ValueError(f"Unknown traffic phase: {phase!r}") from exc
        if requested not in (Phase.NS_GREEN, Phase.EW_GREEN):
            raise ValueError("Demand requests must be NS_GREEN or EW_GREEN")
        self._requested_green = requested

    def tick(self, now: float | None = None) -> Phase:
        current_time = self._clock() if now is None else now
        elapsed = current_time - self._phase_started_at
        next_phase: Phase | None = None

        if self.phase in (Phase.NS_GREEN, Phase.EW_GREEN):
            opposing = Phase.EW_GREEN if self.phase is Phase.NS_GREEN else Phase.NS_GREEN
            if elapsed >= self.min_green_seconds and self._requested_green is opposing:
                next_phase = Phase.NS_YELLOW if self.phase is Phase.NS_GREEN else Phase.EW_YELLOW
        elif self.phase in (Phase.NS_YELLOW, Phase.EW_YELLOW):
            if elapsed >= self.yellow_seconds:
                next_phase = Phase.ALL_RED
        elif elapsed >= self.all_red_seconds and self._requested_green is not None:
            next_phase = self._requested_green

        if next_phase is not None:
            self.phase = next_phase
            self._phase_started_at = current_time
        return self.phase
