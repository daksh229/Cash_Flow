"""
ORM Models - Persisted Tables
=============================
Replaces file-based feature/output exchange with proper DB tables.

Every row carries a tenant_id so a single deployment can serve
multiple entities (client runs 2-3 at launch). Registry/reconciliation/
reporting layers must always filter by tenant.

Tables:
    - feature_snapshots   : versioned feature tables per run
    - forecast_outputs    : unified cash events from S1-S7
    - run_audit           : pipeline run metadata + status
    - event_log           : event bus persistence (for replay)
    - non_po_expenses     : manually-captured expenses outside any PO
    - actual_outcomes     : realised cash events for reconciliation
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, JSON, Index, Text, Boolean,
)

from db.schema import Base


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    feature_set = Column(String(64), nullable=False)
    version = Column(String(32), nullable=False)
    entity_id = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_fs_tenant_set_version_entity",
              "tenant_id", "feature_set", "version", "entity_id"),
    )


class ForecastOutput(Base):
    __tablename__ = "forecast_outputs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    run_id = Column(String(64), nullable=False)
    source_model = Column(String(32), nullable=False)
    entity_id = Column(String(64), nullable=True)
    reference_id = Column(String(64), nullable=True)         # invoice/bill/project id
    event_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    direction = Column(String(8), nullable=False)
    confidence = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_fo_tenant_run_source", "tenant_id", "run_id", "source_model"),
        Index("ix_fo_tenant_date", "tenant_id", "event_date"),
        Index("ix_fo_reference", "reference_id"),
    )


class RunAudit(Base):
    __tablename__ = "run_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    run_id = Column(String(64), nullable=False, unique=True)
    pipeline = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    config_hash = Column(String(64), nullable=True)
    triggered_by = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    event_name = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=True)
    emitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_evlog_tenant_name_processed",
              "tenant_id", "event_name", "processed"),
    )


class NonPOExpense(Base):
    """Manually-captured expense outside any purchase-order workflow.

    SSD gap: many operational expenses live only in emails/budgets/heads
    before they hit the ERP. These rows feed S6.
    """
    __tablename__ = "non_po_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    submitted_by = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False)             # Salary | Tax | Rent | ...
    description = Column(Text, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="INR")
    expected_date = Column(DateTime, nullable=False)
    confidence = Column(Float, nullable=False, default=0.8)
    recurrence = Column(String(16), nullable=True)            # none | monthly | quarterly
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_npe_tenant_date", "tenant_id", "expected_date"),
        Index("ix_npe_tenant_category", "tenant_id", "category"),
    )


class FeatureVersion(Base):
    """Metadata for a feature-store version.

    state lifecycle:   draft -> active -> frozen -> retired

      - draft    : just written, not yet promoted for reads
      - active   : default for fresh predictions
      - frozen   : kept read-only because a downstream artefact
                   (trained model, published forecast) depends on it
      - retired  : superseded; still readable but should not be selected
    """
    __tablename__ = "feature_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    feature_set = Column(String(64), nullable=False)
    version = Column(String(32), nullable=False)
    state = Column(String(16), nullable=False, default="draft")
    config_hash = Column(String(64), nullable=True)
    row_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    frozen_at = Column(DateTime, nullable=True)
    retired_at = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_fv_tenant_set_version", "tenant_id", "feature_set", "version",
              unique=True),
        Index("ix_fv_tenant_set_state", "tenant_id", "feature_set", "state"),
    )


class RecommendationFeedback(Base):
    """User action on a recommendation + realised outcome.

    The RE weight-tuner reads this to nudge scoring_weights based on
    which lever actually moved the needle. Without it, weights would
    stay at the placeholder values Nikunj explicitly called out (Q11).
    """
    __tablename__ = "recommendation_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    recommendation_id = Column(String(64), nullable=False)
    lever = Column(String(32), nullable=False)                # collections | vendor_deferral | expense_deferral
    action = Column(String(16), nullable=False)               # accepted | rejected | ignored
    actor = Column(String(64), nullable=True)
    realised_cash_impact = Column(Float, nullable=True)       # filled in at reconcile time
    predicted_cash_impact = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_rfb_tenant_rec", "tenant_id", "recommendation_id"),
        Index("ix_rfb_tenant_lever_action", "tenant_id", "lever", "action"),
    )


class ModelRegistry(Base):
    """Per-(tenant, model) serving state.

    Used by the serving path to choose which artefact a prediction
    request reads. Promotion is a deliberate action; auto-rollback
    writes a 'retired' row for the old artefact and an 'active' row
    for the replacement.

    state:   active | shadow | retired
      - active  : one row per (tenant, model_key, variant)
      - shadow  : runs in parallel for comparison, not served
      - retired : historical record
    """
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    model_key = Column(String(32), nullable=False)            # s1_ar_prediction, etc
    variant = Column(String(16), nullable=False)              # primary | baseline | prior
    version = Column(String(32), nullable=False)              # pickle hash or run_id
    state = Column(String(16), nullable=False, default="active")
    metric_name = Column(String(32), nullable=True)           # test_mae / test_f1
    metric_value = Column(Float, nullable=True)
    promoted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    retired_at = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_mr_tenant_key_state", "tenant_id", "model_key", "state"),
    )


class IngestionDLQ(Base):
    """Dead-letter queue for ingestion envelopes that could not be
    processed (bad schema, unmapped type, handler error)."""
    __tablename__ = "ingestion_dlq"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=True, default="default")
    envelope_id = Column(String(64), nullable=True)
    source_type = Column(String(64), nullable=True)
    reason = Column(String(32), nullable=False)               # malformed | unmapped | handler_error
    payload = Column(JSON, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_dlq_tenant_reason", "tenant_id", "reason"),
    )


class IngestionSeen(Base):
    """Envelope-id -> processed-at. Used for idempotent ingestion so
    Data Hub can retry a push safely."""
    __tablename__ = "ingestion_seen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    envelope_id = Column(String(64), nullable=False, unique=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ActualOutcome(Base):
    """Realised cash event from the ERP, used to reconcile forecasts.

    Populated by the Data Hub ingestion adapter or manual import. The
    reconciliation job joins this against ForecastOutput to compute
    variance at invoice / bill / aggregate level.
    """
    __tablename__ = "actual_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, default="default")
    reference_id = Column(String(64), nullable=False)         # matches ForecastOutput.reference_id
    source_type = Column(String(16), nullable=False)          # AR | AP | WIP | EXPENSE | OTHER
    actual_date = Column(DateTime, nullable=False)
    actual_amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="INR")
    payload = Column(JSON, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ao_tenant_reference", "tenant_id", "reference_id"),
        Index("ix_ao_tenant_date", "tenant_id", "actual_date"),
    )
