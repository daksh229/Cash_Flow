"""
Recommendation feedback API
===========================
Minimal router: capture a user's accept/reject/ignore action on a
recommendation and (later) attach the realised impact.

Mount in app/api.py:
    from app.routers.recommendations import router as rec_router
    app.include_router(rec_router)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from security.rbac import require_role, Role
from security.tenant_context import tenant_scope
from steps.recommendation_engine.feedback_store import (
    record, attach_realised_impact, VALID_ACTIONS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class FeedbackIn(BaseModel):
    recommendation_id: str
    lever: str = Field(..., description="collections | vendor_deferral | expense_deferral")
    action: str = Field(..., description="accepted | rejected | ignored")
    predicted_cash_impact: Optional[float] = None
    score_components: Optional[dict] = Field(
        default=None,
        description="Optional: {cash_improvement, risk_reduction, target_alignment, feasibility}"
    )


class RealisedImpactIn(BaseModel):
    realised_cash_impact: float


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackIn,
    claims: dict = Depends(require_role(Role.ANALYST)),
    x_tenant_id: Optional[str] = Header(default=None),
):
    if body.action not in VALID_ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"action must be one of {sorted(VALID_ACTIONS)}")
    tenant = x_tenant_id or "default"
    payload = {"score_components": body.score_components} if body.score_components else {}
    with tenant_scope(tenant):
        fid = record(
            recommendation_id=body.recommendation_id,
            lever=body.lever,
            action=body.action,
            predicted_cash_impact=body.predicted_cash_impact,
            actor=claims.get("sub", "unknown"),
            payload=payload,
            tenant_id=tenant,
        )
    return {"id": fid, "status": "recorded"}


@router.post("/{recommendation_id}/realised", status_code=status.HTTP_200_OK)
def submit_realised(
    recommendation_id: str,
    body: RealisedImpactIn,
    claims: dict = Depends(require_role(Role.ANALYST)),
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant = x_tenant_id or "default"
    with tenant_scope(tenant):
        ok = attach_realised_impact(
            recommendation_id=recommendation_id,
            realised=body.realised_cash_impact,
            tenant_id=tenant,
        )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recommendation not found")
    return {"status": "updated"}
