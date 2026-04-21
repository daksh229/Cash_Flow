"""
Metrics Registry
================
Prometheus-compatible counters/gauges/histograms. Uses prometheus_client
if installed; falls back to an in-process dict so tests and local runs
don't require the dependency.

Exposed metrics (initial):
  cashflow_runs_total{pipeline,status}       : pipeline run counter
  cashflow_run_duration_seconds{pipeline}    : histogram
  cashflow_model_mae{model}                  : gauge, per-model latest MAE
  cashflow_events_emitted_total{name}        : event bus traffic
  cashflow_db_errors_total                   : DB-layer failures
"""

import logging
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest
    _PROM = True
except ImportError:
    _PROM = False


class _FallbackMetric:
    def __init__(self, name):
        self.name = name
        self.values = {}

    def labels(self, **kwargs):
        key = tuple(sorted(kwargs.items()))
        self.values.setdefault(key, 0)
        self._last_key = key
        return self

    def inc(self, n=1):
        self.values[self._last_key] = self.values.get(self._last_key, 0) + n

    def set(self, v):
        self.values[self._last_key] = v

    def observe(self, v):
        self.values.setdefault(self._last_key, [])
        self.values[self._last_key].append(v)


class MetricsRegistry:
    def __init__(self):
        if _PROM:
            self.registry = CollectorRegistry()
            self.runs_total = Counter(
                "cashflow_runs_total", "Pipeline runs",
                ["pipeline", "status"], registry=self.registry,
            )
            self.run_duration = Histogram(
                "cashflow_run_duration_seconds", "Pipeline duration",
                ["pipeline"], registry=self.registry,
            )
            self.model_mae = Gauge(
                "cashflow_model_mae", "Latest test MAE per model",
                ["model"], registry=self.registry,
            )
            self.events_total = Counter(
                "cashflow_events_emitted_total", "Events emitted",
                ["name"], registry=self.registry,
            )
            self.db_errors = Counter(
                "cashflow_db_errors_total", "DB layer errors",
                registry=self.registry,
            )
        else:
            self.registry = None
            self.runs_total = _FallbackMetric("cashflow_runs_total")
            self.run_duration = _FallbackMetric("cashflow_run_duration_seconds")
            self.model_mae = _FallbackMetric("cashflow_model_mae")
            self.events_total = _FallbackMetric("cashflow_events_emitted_total")
            self.db_errors = _FallbackMetric("cashflow_db_errors_total")

    @contextmanager
    def time_run(self, pipeline):
        start = time.time()
        try:
            yield
            status = "success"
        except Exception:
            status = "failed"
            raise
        finally:
            dur = time.time() - start
            self.run_duration.labels(pipeline=pipeline).observe(dur)
            self.runs_total.labels(pipeline=pipeline, status=status).inc()

    def export_prometheus(self) -> bytes:
        if not _PROM:
            return b"# prometheus_client not installed\n"
        return generate_latest(self.registry)


metrics = MetricsRegistry()
