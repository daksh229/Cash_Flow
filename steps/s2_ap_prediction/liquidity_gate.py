"""
S2 - Liquidity Gate
===================
Gates recommended vendor payments against projected available cash.
Per the SSD, S2 should not just predict when bills *would* be paid - it
must also decide which bills *can* be paid without breaching the
treasury floor on the payment date.

Inputs:
    predictions : DataFrame with columns
                  [bill_id, vendor_id, predicted_payment_date, amount, priority]
    cash_ledger : DataFrame with columns
                  [date, projected_balance]   (from S7)
    config      : model_cfg["liquidity_gate"]:
                    min_cash_floor, critical_priorities, apply_grace_days

Output:
    Same rows annotated with:
        gate_decision    : pay | defer | partial
        deferred_to      : date (if gate_decision != pay)
        shortfall_amount : float
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _floor_for_day(ledger: pd.DataFrame, day) -> float:
    row = ledger.loc[ledger["date"] == day]
    if row.empty:
        return float("inf")
    return float(row.iloc[0]["projected_balance"])


def apply(predictions: pd.DataFrame, cash_ledger: pd.DataFrame, gate_cfg: dict) -> pd.DataFrame:
    min_floor = float(gate_cfg.get("min_cash_floor", 0.0))
    critical = set(gate_cfg.get("critical_priorities", ["payroll", "tax"]))
    grace_days = int(gate_cfg.get("apply_grace_days", 5))

    df = predictions.copy()
    df["predicted_payment_date"] = pd.to_datetime(df["predicted_payment_date"])
    df = df.sort_values(["predicted_payment_date", "priority"])

    ledger = cash_ledger.copy()
    ledger["date"] = pd.to_datetime(ledger["date"])
    running = ledger.set_index("date")["projected_balance"].to_dict()

    decisions, deferred, shortfalls = [], [], []

    for _, row in df.iterrows():
        d = row["predicted_payment_date"]
        amt = float(row["amount"])
        prio = row.get("priority", "normal")
        balance = running.get(d, float("inf"))
        projected_after = balance - amt

        if projected_after >= min_floor or prio in critical:
            decisions.append("pay")
            deferred.append(pd.NaT)
            shortfalls.append(0.0)
            running[d] = projected_after
            continue

        pushed_to, resolved = d, False
        for k in range(1, grace_days + 1):
            candidate = d + pd.Timedelta(days=k)
            if running.get(candidate, float("inf")) - amt >= min_floor:
                pushed_to = candidate
                running[candidate] = running.get(candidate, 0.0) - amt
                resolved = True
                break

        if resolved:
            decisions.append("defer")
            deferred.append(pushed_to)
            shortfalls.append(0.0)
        else:
            decisions.append("partial")
            deferred.append(pushed_to)
            shortfalls.append(round(min_floor - projected_after, 2))

    df["gate_decision"] = decisions
    df["deferred_to"] = deferred
    df["shortfall_amount"] = shortfalls

    summary = df["gate_decision"].value_counts().to_dict()
    logger.info("liquidity_gate decisions: %s (floor=%s)", summary, min_floor)
    return df


def run(predictions, cash_ledger, model_cfg):
    gate_cfg = model_cfg.get("liquidity_gate", {})
    return apply(predictions, cash_ledger, gate_cfg)
