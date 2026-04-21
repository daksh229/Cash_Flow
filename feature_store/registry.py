"""
Feature Registry
================
Write/read interface for the persisted feature store. Wraps db.models.FeatureSnapshot
so modules (S1..S7) stop reading/writing CSVs from Data/features/ and instead
go through a versioned, queryable layer.

Feature sets are declared once here so downstream consumers can validate
the set name before reading.
"""

import logging
import pandas as pd

from db.connection import get_session
from db.models import FeatureSnapshot
from feature_store.versioning import current_version
from feature_store.version_policy import register as register_version
from feature_store.version_policy import resolve_active_version
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)

KNOWN_FEATURE_SETS = {
    "customer_features",
    "invoice_features",
    "vendor_features",
    "bill_features",
    "project_features",
    "expense_features",
}


class FeatureRegistry:
    def __init__(self, feature_set):
        if feature_set not in KNOWN_FEATURE_SETS:
            raise ValueError(
                f"Unknown feature set '{feature_set}'. "
                f"Register in feature_store.registry.KNOWN_FEATURE_SETS first."
            )
        self.feature_set = feature_set

    def write(self, df, entity_col, version=None, tenant_id=None):
        version = version or current_version()
        tenant_id = tenant_id or current_tenant()
        records = [
            FeatureSnapshot(
                tenant_id=tenant_id,
                feature_set=self.feature_set,
                version=version,
                entity_id=str(row[entity_col]),
                payload={k: _jsonable(v) for k, v in row.items()},
            )
            for _, row in df.iterrows()
        ]
        with get_session() as session:
            session.add_all(records)
            session.commit()
        register_version(
            feature_set=self.feature_set,
            version=version,
            row_count=len(records),
            tenant_id=tenant_id,
        )
        logger.info(
            "Wrote %d rows to feature_store[%s] tenant=%s version=%s (draft)",
            len(records), self.feature_set, tenant_id, version,
        )
        return version

    def read(self, version=None, entity_ids=None, tenant_id=None):
        tenant_id = tenant_id or current_tenant()
        if version is None:
            version = resolve_active_version(self.feature_set, tenant_id) or current_version()
        with get_session() as session:
            q = session.query(FeatureSnapshot).filter(
                FeatureSnapshot.tenant_id == tenant_id,
                FeatureSnapshot.feature_set == self.feature_set,
                FeatureSnapshot.version == version,
            )
            if entity_ids is not None:
                q = q.filter(FeatureSnapshot.entity_id.in_([str(e) for e in entity_ids]))
            rows = q.all()
        if not rows:
            logger.warning(
                "feature_store[%s] tenant=%s version=%s returned 0 rows",
                self.feature_set, tenant_id, version,
            )
            return pd.DataFrame()
        return pd.DataFrame([r.payload for r in rows])


def _jsonable(v):
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v
