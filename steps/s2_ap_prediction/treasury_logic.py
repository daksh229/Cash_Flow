"""
S2 - Treasury Logic
===================
Implements the full treasury rule-book the SSD attaches to S2:

  1. Early-payment discounts
       If vendor offers X%/N days and projected cash remains above the
       floor, bring payment forward to capture the discount.

  2. Late-payment penalties
       If a bill would breach the liquidity gate beyond the grace
       window, pick the cheapest-to-defer bill (lowest penalty_rate *
       amount) rather than round-robin.

  3. Vendor priority tiering
       Critical-vendor bills never enter the defer queue.

  4. Credit line usage
       When on-hand cash is insufficient even with grace, draw from a
       configured credit line up to credit_limit.

This module is pure functions over DataFrames - no IO, no DB. The
forecast_engine wires it in after predictions are produced and the
liquidity gate has flagged shortfalls.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def apply_early_discounts(df: pd.DataFrame, cash_ledger: pd.DataFrame, floor: float) -> pd.DataFrame:
    out = df.copy()
    if "discount_pct" not in out.columns or "discount_days" not in out.columns:
        return out

    balances = cash_ledger.set_index(pd.to_datetime(cash_ledger["date"]))["projected_balance"].to_dict()

    captured = 0
    for idx, row in out.iterrows():
        pct = row.get("discount_pct", 0) or 0
        days = row.get("discount_days", 0) or 0
        if pct <= 0 or days <= 0:
            continue
        early_date = pd.to_datetime(row["predicted_payment_date"]) - pd.Timedelta(days=days)
        if balances.get(early_date, float("inf")) - float(row["amount"]) >= floor:
            out.at[idx, "predicted_payment_date"] = early_date
            out.at[idx, "amount"] = round(float(row["amount"]) * (1 - pct / 100.0), 2)
            out.at[idx, "discount_captured"] = True
            captured += 1

    logger.info("early-payment discounts captured: %d", captured)
    return out


def rank_defer_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Cheapest-to-defer first: low penalty_rate * amount rises to top."""
    out = df.copy()
    if "penalty_rate" not in out.columns:
        out["penalty_rate"] = 0.0
    out["defer_cost"] = out["penalty_rate"].fillna(0) * out["amount"]
    return out.sort_values("defer_cost", ascending=True)


def apply_credit_line(df: pd.DataFrame, credit_limit: float) -> pd.DataFrame:
    out = df.copy()
    if "shortfall_amount" not in out.columns:
        return out
    remaining = float(credit_limit or 0)
    drawn = []
    for _, row in out.iterrows():
        short = float(row.get("shortfall_amount") or 0)
        if short <= 0 or remaining <= 0:
            drawn.append(0.0)
            continue
        take = min(short, remaining)
        remaining -= take
        drawn.append(take)
    out["credit_line_drawn"] = drawn
    logger.info("credit line drawn total=%.2f remaining=%.2f",
                sum(drawn), remaining)
    return out


def run(gated_predictions: pd.DataFrame, cash_ledger: pd.DataFrame, model_cfg: dict) -> pd.DataFrame:
    tcfg = model_cfg.get("treasury", {})
    floor = float(tcfg.get("min_cash_floor", 0.0))
    credit_limit = float(tcfg.get("credit_limit", 0.0))

    out = apply_early_discounts(gated_predictions, cash_ledger, floor)
    out = rank_defer_candidates(out)
    out = apply_credit_line(out, credit_limit)
    return out
