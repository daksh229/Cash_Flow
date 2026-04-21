"""
Tenant Context
==============
Request-scoped tenant selector. FastAPI/async code sets the active
tenant for the duration of a request; background jobs set it explicitly.

Everything that reads/writes the DB must resolve tenant through
`current_tenant()` instead of hardcoding `"default"`.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar

_tenant_var: ContextVar[str] = ContextVar("tenant_id", default=None)


def current_tenant() -> str:
    return _tenant_var.get() or os.environ.get("CASHFLOW_TENANT_ID") or "default"


@contextmanager
def tenant_scope(tenant_id: str):
    token = _tenant_var.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _tenant_var.reset(token)


def set_tenant(tenant_id: str):
    """For long-running jobs where a context manager is awkward."""
    _tenant_var.set(tenant_id)
