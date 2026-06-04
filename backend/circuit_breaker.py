"""
Simple in-process circuit breaker for external service calls.

Usage:
    cb = CircuitBreaker("openai", failure_threshold=5, recovery_timeout=60)

    async with cb:
        result = await openai_client.chat(...)

States: CLOSED (normal) -> OPEN (tripping) -> HALF_OPEN (probing)
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a circuit breaker is OPEN and the call is rejected."""
    def __init__(self, name: str):
        super().__init__(f"Circuit breaker '{name}' is OPEN -- call rejected")
        self.breaker_name = name


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: tuple = (Exception,),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        if self._state == State.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = State.HALF_OPEN
                logger.info("circuit_breaker: '%s' -> HALF_OPEN (probing)", self.name)
        return self._state

    async def __aenter__(self):
        async with self._lock:
            if self.state == State.OPEN:
                raise CircuitBreakerOpen(self.name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type and issubclass(exc_type, self.expected_exceptions):
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                if self._failure_count >= self.failure_threshold:
                    if self._state != State.OPEN:
                        self._state = State.OPEN
                        logger.warning(
                            "circuit_breaker: '%s' -> OPEN after %d failures",
                            self.name, self._failure_count,
                        )
                return False  # Don't suppress the exception
            else:
                # Success -- reset
                if self._state == State.HALF_OPEN:
                    logger.info("circuit_breaker: '%s' -> CLOSED (recovered)", self.name)
                self._state = State.CLOSED
                self._failure_count = 0
                return False


# Pre-built breakers for known external services
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a named circuit breaker (module-level singletons)."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, **kwargs)
    return _breakers[name]


# Convenience instances
ai_breaker = CircuitBreaker("ai_provider", failure_threshold=5, recovery_timeout=30)
webhook_breaker = CircuitBreaker("webhook_delivery", failure_threshold=10, recovery_timeout=60)
