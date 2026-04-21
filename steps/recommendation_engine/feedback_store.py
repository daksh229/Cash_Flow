"""
Recommendation Feedback Store
=============================
Captures what the treasury user did with each recommendation (accept /
reject / ignore) and, later, the realised cash impact so the weight
tuner can learn.

This is the storage layer; the API endpoint lives in
app/routers/recommendations.py and the learning loop in weight_tuner.py.
"""

import logging
from typing import Dict, List, Optional

from db.connection import get_session
from db.models import RecommendationFeedback
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"accepted", "rejected", "ignored"}


def record(recommendation_id: str, lever: str, action: str,
           predicted_cash_impact: Optional[float] = None,
           actor: Optional[str] = None,
           payload: Optional[Dict] = None,
           tenant_id: Optional[str] = None) -> int:
    if action not in VALID_ACTIONS:
        raise ValueError(f"action must be one of {VALID_ACTIONS}")

    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = RecommendationFeedback(
            tenant_id=tenant_id,
            recommendation_id=str(recommendation_id),
            lever=lever,
            action=action,
            actor=actor,
            predicted_cash_impact=predicted_cash_impact,
            payload=payload or {},
        )
        s.add(row)
        s.commit()
        return row.id


def attach_realised_impact(recommendation_id: str, realised: float,
                           tenant_id: Optional[str] = None) -> bool:
    """Called by reconciliation once the ERP shows the outcome."""
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = s.query(RecommendationFeedback).filter_by(
            tenant_id=tenant_id, recommendation_id=recommendation_id,
        ).order_by(RecommendationFeedback.id.desc()).first()
        if row is None:
            return False
        row.realised_cash_impact = float(realised)
        s.commit()
        return True


def load_training_frame(tenant_id: Optional[str] = None) -> List[Dict]:
    """Return rows usable by weight_tuner: accepted + has realised impact."""
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        rows = s.query(RecommendationFeedback).filter(
            RecommendationFeedback.tenant_id == tenant_id,
            RecommendationFeedback.action == "accepted",
            RecommendationFeedback.realised_cash_impact.isnot(None),
        ).all()
    return [
        {
            "lever": r.lever,
            "predicted": r.predicted_cash_impact,
            "realised": r.realised_cash_impact,
            "payload": r.payload or {},
        }
        for r in rows
    ]
