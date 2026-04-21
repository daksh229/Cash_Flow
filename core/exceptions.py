"""
Domain Exceptions
=================
Centralised exception hierarchy. Modules should raise the most specific
subclass so the DAG/retry layer can decide: retry, skip, or fail loudly.

Rule of thumb:
  - ConfigError / DataValidationError  -> fail fast, no retry
  - UpstreamDataMissing                -> skip + requeue via event bus
  - ExternalServiceError               -> retry with backoff
  - ModelTrainingError                 -> fail, record in run_audit
"""


class CashFlowError(Exception):
    """Base class for all domain errors."""


class ConfigError(CashFlowError):
    """Invalid or missing configuration values."""


class DataValidationError(CashFlowError):
    """Input data failed schema or business-rule validation."""


class UpstreamDataMissing(CashFlowError):
    """A required upstream table/feature is absent."""


class ModelTrainingError(CashFlowError):
    """Training failed (NaNs, empty set, solver divergence, etc.)."""


class ExternalServiceError(CashFlowError):
    """Transient failure of an external dependency (DB, MLflow, queue)."""
