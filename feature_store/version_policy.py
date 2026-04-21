"""
Feature Version Policy
======================
Closes the Q4 gap: "when feature logic changes, what happens to
in-flight predictions that used an older version?"

Policy
------
1. A new write starts a version in state `draft`.
2. `promote(version)` moves `active` -> `retired` and `draft` -> `active`
   for the same (tenant, feature_set). Only one active per pair.
3. Any trained model / published forecast that read a version pins
   that version via `freeze(version, reason=...)`. Frozen versions are
   retained even after retirement so the artefact stays reproducible.
4. `stale_check(max_age_hours)` flags active versions whose payload
   age exceeds a threshold - the ingestion layer should trigger a
   rebuild before serving from them.

Readers (the registry.read path) always resolve through
`resolve_active_version()` instead of taking whatever the caller
passes in.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from db.connection import get_session
from db.models import FeatureVersion
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)


def register(feature_set: str, version: str, row_count: int,
             config_hash: Optional[str] = None,
             tenant_id: Optional[str] = None) -> int:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        existing = s.query(FeatureVersion).filter_by(
            tenant_id=tenant_id, feature_set=feature_set, version=version,
        ).one_or_none()
        if existing:
            existing.row_count = row_count
            if config_hash:
                existing.config_hash = config_hash
            s.commit()
            return existing.id
        row = FeatureVersion(
            tenant_id=tenant_id, feature_set=feature_set, version=version,
            state="draft", row_count=row_count, config_hash=config_hash,
        )
        s.add(row)
        s.commit()
        return row.id


def promote(feature_set: str, version: str, tenant_id: Optional[str] = None) -> dict:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        previous = s.query(FeatureVersion).filter_by(
            tenant_id=tenant_id, feature_set=feature_set, state="active",
        ).all()
        for p in previous:
            p.state = "retired"
            p.retired_at = datetime.utcnow()
            p.reason = f"superseded by {version}"

        target = s.query(FeatureVersion).filter_by(
            tenant_id=tenant_id, feature_set=feature_set, version=version,
        ).one_or_none()
        if target is None:
            raise LookupError(f"version '{version}' not registered")
        target.state = "active"
        s.commit()
        logger.info(
            "promoted %s/%s -> active (retired %d previous)",
            feature_set, version, len(previous),
        )
        return {"active": version, "retired": [p.version for p in previous]}


def freeze(feature_set: str, version: str, reason: str,
           tenant_id: Optional[str] = None) -> None:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = s.query(FeatureVersion).filter_by(
            tenant_id=tenant_id, feature_set=feature_set, version=version,
        ).one_or_none()
        if row is None:
            raise LookupError(f"version '{version}' not registered")
        row.state = "frozen"
        row.frozen_at = datetime.utcnow()
        row.reason = reason
        s.commit()
        logger.info("froze %s/%s (%s)", feature_set, version, reason)


def resolve_active_version(feature_set: str,
                           tenant_id: Optional[str] = None) -> Optional[str]:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = s.query(FeatureVersion).filter_by(
            tenant_id=tenant_id, feature_set=feature_set, state="active",
        ).order_by(FeatureVersion.created_at.desc()).first()
        return row.version if row else None


def stale_check(feature_set: str, max_age_hours: int,
                tenant_id: Optional[str] = None) -> Optional[dict]:
    """Return details if the active version is older than max_age_hours."""
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = s.query(FeatureVersion).filter_by(
            tenant_id=tenant_id, feature_set=feature_set, state="active",
        ).first()
        if row is None:
            return {"feature_set": feature_set, "status": "no_active_version"}
        age = datetime.utcnow() - row.created_at
        stale = age > timedelta(hours=max_age_hours)
        return {
            "feature_set": feature_set,
            "version": row.version,
            "age_hours": round(age.total_seconds() / 3600, 2),
            "stale": stale,
        }
