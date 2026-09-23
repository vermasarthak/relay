from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Optional

class Clock(ABC):
    """Abstract clock interface for deterministic time management."""
    @abstractmethod
    def now(self) -> datetime:
        """Returns the current UTC timestamp."""
        pass

    @abstractmethod
    def sleep(self, seconds: float) -> None:
        """Sleeps or advances time."""
        pass


class SystemClock(Clock):
    """Production system clock using real UTC time."""
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        import time
        time.sleep(seconds)


class TestClock(Clock):
    """Deterministic, fast-forwardable clock for unit and durability testing."""
    def __init__(self, initial_time: Optional[datetime] = None):
        if initial_time is None:
            self._current_time = datetime.now(timezone.utc)
        else:
            if initial_time.tzinfo is None:
                self._current_time = initial_time.replace(tzinfo=timezone.utc)
            else:
                self._current_time = initial_time

    def now(self) -> datetime:
        return self._current_time

    def advance(self, seconds: float) -> datetime:
        self._current_time += timedelta(seconds=seconds)
        return self._current_time

    def set(self, new_time: datetime) -> None:
        if new_time.tzinfo is None:
            self._current_time = new_time.replace(tzinfo=timezone.utc)
        else:
            self._current_time = new_time

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)

# Global default clock instance
_default_clock: Clock = SystemClock()

def get_clock() -> Clock:
    return _default_clock

def set_clock(clock: Clock) -> None:
    global _default_clock
    _default_clock = clock
