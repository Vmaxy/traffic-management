"""Timed, conflict-safe signal phase state machine."""

from __future__ import annotations

import math
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
        min_green_seconds: float = 3.0,
        yellow_seconds: float = 2.0,
        all_red_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        max_green_seconds: float = 30.0,
    ) -> None:
        intervals = (min_green_seconds, yellow_seconds, all_red_seconds, max_green_seconds)
        if any(not math.isfinite(value) or value <= 0 for value in intervals):
            raise ValueError("all FSM timing intervals must be greater than zero")
        if max_green_seconds < min_green_seconds:
            raise ValueError("max_green_seconds must be at least min_green_seconds")
        self.min_green_seconds = min_green_seconds
        self.yellow_seconds = yellow_seconds
        self.all_red_seconds = all_red_seconds
        self.max_green_seconds = max_green_seconds
        self._clock = clock
        self.phase = Phase.ALL_RED
        started_at = clock()
        if not math.isfinite(started_at):
            raise ValueError("clock must return a finite monotonic time")
        self._phase_started_at = started_at
        self._last_tick_at = started_at
        self._requested_green: Phase | None = None
        self._emergency_priority = False
        self._forced_green: Phase | None = None

    @property
    def elapsed_seconds(self) -> float:
        """Time spent in the current phase, for diagnostics and the video HUD."""
        return max(0.0, self._clock() - self._phase_started_at)

    def request_phase(self, phase: Phase | str, emergency: bool = False) -> None:
        try:
            requested = phase if isinstance(phase, Phase) else Phase(phase)
        except ValueError as exc:
            raise ValueError(f"Unknown traffic phase: {phase!r}") from exc
        if requested not in (Phase.NS_GREEN, Phase.EW_GREEN):
            raise ValueError("Demand requests must be NS_GREEN or EW_GREEN")
        if self._forced_green is None or emergency:
            self._requested_green = requested
        self._emergency_priority = bool(emergency)
        if emergency:
            self._forced_green = None

    def tick(self, now: float | None = None) -> Phase:
        current_time = self._clock() if now is None else now
        if not math.isfinite(current_time) or current_time < self._last_tick_at:
            raise ValueError("tick time must be finite and monotonic")
        self._last_tick_at = current_time
        elapsed = current_time - self._phase_started_at
        next_phase: Phase | None = None

        if self.phase in (Phase.NS_GREEN, Phase.EW_GREEN):
            is_ns = self.phase is Phase.NS_GREEN
            opposing = Phase.EW_GREEN if is_ns else Phase.NS_GREEN
            active_yellow = Phase.NS_YELLOW if is_ns else Phase.EW_YELLOW
            request_opposing = self._requested_green is opposing
            if elapsed >= self.max_green_seconds:
                self._requested_green = opposing
                self._forced_green = opposing
                request_opposing = True
            if elapsed >= self.min_green_seconds and (
                request_opposing or self._emergency_priority
            ):
                next_phase = active_yellow
        elif self.phase in (Phase.NS_YELLOW, Phase.EW_YELLOW):
            if elapsed >= self.yellow_seconds:
                next_phase = Phase.ALL_RED
        elif elapsed >= self.all_red_seconds and self._requested_green is not None:
            next_phase = self._requested_green
            self._forced_green = None

        if next_phase is not None:
            self.phase = next_phase
            self._phase_started_at = current_time
            if next_phase in (Phase.NS_YELLOW, Phase.EW_YELLOW):
                self._emergency_priority = False
        return self.phase
