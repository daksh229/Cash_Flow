"""
Non-PO Expense API
==================
Client Q&A row 2: many operational expenses (legal fees, ad-hoc travel,
ad spends, consultancy) never go through a purchase order - they live
in emails, budgets, and people's heads until they hit the ERP.

This router captures them at commitment time so S6 has visibility
before the bill shows up. Emits a `bill.created`-style event so the
S2/S6 subgraph can re-score.

Mount in app/api.py:
    from app.routers.non_po_expenses import router as non_po_router
    app.include_router(non_po_router)
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field

from db.connection import get_session
from db.models import NonPOExpense
from events.event_bus import bus
from events.triggers import EventName
from security.rbac import require_role, Role
from security.tenant_context import tenant_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/expenses/non-po", tags=["non-po-expenses"])


class NonPOExpenseIn(BaseModel):
    category: str = Field(..., description="Salary | Tax | Rent | Legal | Ad | Other")
    description: Optional[str] = None
    amount: float = Field(..., gt=0)
    currency: str = "INR"
    expected_date: datetime
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    recurrence: Optional[str] = Field(None, description="none | monthly | quarterly")


class NonPOExpenseOut(NonPOExpenseIn):
    id: int
    submitted_by: str
    is_active: bool
    created_at: datetime


def _resolve_tenant(x_tenant_id: Optional[str]) -> str:
    return x_tenant_id or "default"


@router.post("", status_code=status.HTTP_201_CREATED, response_model=NonPOExpenseOut)
def create(
    body: NonPOExpenseIn,
    claims: dict = Depends(require_role(Role.ANALYST)),
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant = _resolve_tenant(x_tenant_id)
    with tenant_scope(tenant):
        with get_session() as s:
            row = NonPOExpense(
                tenant_id=tenant,
                submitted_by=claims.get("sub", "unknown"),
                category=body.category,
                description=body.description,
                amount=body.amount,
                currency=body.currency,
                expected_date=body.expected_date,
                confidence=body.confidence,
                recurrence=body.recurrence,
                is_active=True,
            )
            s.add(row)
            s.commit()
            created = NonPOExpenseOut(
                id=row.id, submitted_by=row.submitted_by, is_active=row.is_active,
                created_at=row.created_at, category=row.category,
                description=row.description, amount=row.amount,
                currency=row.currency, expected_date=row.expected_date,
                confidence=row.confidence, recurrence=row.recurrence,
            )

        bus.emit(EventName.BILL_CREATED, {
            "source": "non_po_expense",
            "non_po_id": created.id,
            "amount": created.amount,
            "expected_date": created.expected_date.isoformat(),
        })
    return created


@router.get("")
def list_active(
    claims: dict = Depends(require_role(Role.VIEWER)),
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant = _resolve_tenant(x_tenant_id)
    with get_session() as s:
        rows = (
            s.query(NonPOExpense)
            .filter(NonPOExpense.tenant_id == tenant, NonPOExpense.is_active == True)  # noqa: E712
            .order_by(NonPOExpense.expected_date)
            .all()
        )
    return [
        {
            "id": r.id, "category": r.category, "description": r.description,
            "amount": r.amount, "currency": r.currency,
            "expected_date": r.expected_date.isoformat(),
            "confidence": r.confidence, "recurrence": r.recurrence,
            "submitted_by": r.submitted_by,
        } for r in rows
    ]


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(
    expense_id: int,
    claims: dict = Depends(require_role(Role.ANALYST)),
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant = _resolve_tenant(x_tenant_id)
    with get_session() as s:
        row = s.query(NonPOExpense).filter(
            NonPOExpense.id == expense_id,
            NonPOExpense.tenant_id == tenant,
        ).one_or_none()
        if row is None:
            raise HTTPException(404, "not found")
        row.is_active = False
        s.commit()
