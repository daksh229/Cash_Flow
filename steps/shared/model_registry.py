"""
Model Registry
==============
Per-(tenant, model, variant) serving state. Complements model_selector:

  - selector picks which variant to call for a single prediction
  - registry records WHICH variant is promoted as 'active' and lets
    the serving path read that decision from one place rather than
    re-deriving it on every call

States
------
  active   : serve this one. Exactly one per (tenant, model_key, variant)
             -- but a model_key can have multiple variants simultaneously
             active (primary + baseline for champion/challenger).
  shadow   : compute predictions in parallel for comparison; do NOT serve.
  retired  : historical. Kept for audit/rollback.

Auto-rollback flow
------------------
  1. Evaluator detects LGB degradation > threshold.
  2. Calls demote(tenant, model_key, "primary").
  3. Calls promote(tenant, model_key, "baseline", version, metric).
  4. model_selector then sees the new active state on the next call.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from db.connection import get_session
from db.models import ModelRegistry
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)

VALID_STATES = {"active", "shadow", "retired"}
VALID_VARIANTS = {"primary", "baseline", "prior"}


def promote(model_key: str, variant: str, version: str,
            metric_name: Optional[str] = None,
            metric_value: Optional[float] = None,
            reason: Optional[str] = None,
            tenant_id: Optional[str] = None) -> int:
    if variant not in VALID_VARIANTS:
        raise ValueError(f"variant must be one of {VALID_VARIANTS}")
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        previous = s.query(ModelRegistry).filter_by(
            tenant_id=tenant_id, model_key=model_key,
            variant=variant, state="active",
        ).all()
        for p in previous:
            p.state = "retired"
            p.retired_at = datetime.utcnow()
            p.reason = reason or f"superseded by {version}"

        row = ModelRegistry(
            tenant_id=tenant_id, model_key=model_key, variant=variant,
            version=version, state="active",
            metric_name=metric_name, metric_value=metric_value,
            reason=reason,
        )
        s.add(row)
        s.commit()
        logger.info(
            "promoted %s/%s variant=%s version=%s (retired %d previous)",
            tenant_id, model_key, variant, version, len(previous),
        )
        return row.id


def demote(model_key: str, variant: str,
           reason: Optional[str] = None,
           tenant_id: Optional[str] = None) -> int:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        rows = s.query(ModelRegistry).filter_by(
            tenant_id=tenant_id, model_key=model_key,
            variant=variant, state="active",
        ).all()
        for r in rows:
            r.state = "retired"
            r.retired_at = datetime.utcnow()
            r.reason = reason or "demoted"
        s.commit()
        logger.info("demoted %s/%s variant=%s (%d rows)",
                    tenant_id, model_key, variant, len(rows))
        return len(rows)


def set_shadow(model_key: str, variant: str, version: str,
               tenant_id: Optional[str] = None) -> int:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = ModelRegistry(
            tenant_id=tenant_id, model_key=model_key, variant=variant,
            version=version, state="shadow",
        )
        s.add(row)
        s.commit()
        logger.info("shadow %s/%s variant=%s version=%s",
                    tenant_id, model_key, variant, version)
        return row.id


def active_variants(model_key: str,
                    tenant_id: Optional[str] = None) -> List[Dict]:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        rows = s.query(ModelRegistry).filter_by(
            tenant_id=tenant_id, model_key=model_key, state="active",
        ).all()
    return [
        {"variant": r.variant, "version": r.version,
         "metric_name": r.metric_name, "metric_value": r.metric_value}
        for r in rows
    ]


def history(model_key: str, tenant_id: Optional[str] = None) -> List[Dict]:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        rows = s.query(ModelRegistry).filter_by(
            tenant_id=tenant_id, model_key=model_key,
        ).order_by(ModelRegistry.promoted_at.desc()).all()
    return [
        {"variant": r.variant, "version": r.version, "state": r.state,
         "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
         "retired_at": r.retired_at.isoformat() if r.retired_at else None,
         "reason": r.reason}
        for r in rows
    ]
