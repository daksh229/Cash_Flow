"""
Circuit Breaker
===============
Guards against cascading failures when an external dependency (DB, MLflow,
model server) is down. After N consecutive failures the breaker opens and
fast-fails all calls for `reset_after` seconds, then goes half-open for
one probe call before deciding to close or reopen.

This pairs with retry: use retry for transient hiccups, breaker for a
dependency that is clearly unhealthy.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, name, failure_threshold=5, reset_after=30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self._failures = 0
        self._state = self.CLOSED
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self):
        return self._state

    def _transition(self, new_state):
        logger.info("breaker[%s] %s -> %s", self.name, self._state, new_state)
        self._state = new_state

    def call(self, fn, *args, **kwargs):
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._opened_at >= self.reset_after:
                    self._transition(self.HALF_OPEN)
                else:
                    raise CircuitOpenError(f"circuit '{self.name}' is open")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
                    self._transition(self.OPEN)
                    self._opened_at = time.time()
            raise
        with self._lock:
            self._failures = 0
            if self._state != self.CLOSED:
                self._transition(self.CLOSED)
        return result

    def __call__(self, fn):
        import functools

        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            return self.call(fn, *args, **kwargs)
        return _wrapped
