import pytest

from core.retry import retry
from core.exceptions import ExternalServiceError, DataValidationError
from core.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_retry_succeeds_after_transient_failure():
    calls = {"n": 0}

    @retry(attempts=3, base_delay=0)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ExternalServiceError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2


def test_retry_does_not_swallow_non_retryable():
    @retry(attempts=3, base_delay=0)
    def bad():
        raise DataValidationError("schema off")

    with pytest.raises(DataValidationError):
        bad()


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker("t", failure_threshold=2, reset_after=60)

    def boom():
        raise RuntimeError("x")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(boom)
    with pytest.raises(CircuitOpenError):
        cb.call(boom)


def test_circuit_half_open_then_closes(monkeypatch):
    cb = CircuitBreaker("t", failure_threshold=1, reset_after=0)

    def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        cb.call(boom)
    assert cb.state == "open"
    assert cb.call(lambda: 42) == 42
    assert cb.state == "closed"
