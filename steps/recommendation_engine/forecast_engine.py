"""
Recommendation Engine - Engine
====================================
Components:
  a. Scenario Generator - generates alternative scenarios per lever
  b. Collections Improvement - prioritise overdue invoices for escalation
  c. Evaluation & Ranking - weighted scoring function
  d. Recommendation Generator - plain-language actionable advice
"""

import logging
import yaml
import uuid
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("re.engine")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "recommendation_engine.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(input_data, config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("RECOMMENDATION ENGINE - START")
    logger.info("=" * 60)

    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    weights = config.get("scoring_weights", {})
    levers = config.get("levers", {})
    constraints = config.get("constraints", {})
    top_n = config.get("output", {}).get("top_n", 10)

    w1 = weights.get("cash_improvement", 0.40)
    w2 = weights.get("risk_reduction", 0.30)
    w3 = weights.get("target_alignment", 0.20)
    w4 = weights.get("feasibility", 0.10)
    min_cash = constraints.get("min_cash_balance", 1000000)

    s7_daily = input_data.get("s7_daily", pd.DataFrame())
    overdue = input_data.get("overdue_invoices", pd.DataFrame())

    all_recommendations = []

    # ==================================================================
    # a. COLLECTIONS IMPROVEMENT LEVER
    # ==================================================================
    coll_cfg = levers.get("collections", {})
    if coll_cfg.get("enabled", True) and not overdue.empty:
        logger.info("--- Lever: Collections Acceleration ---")

        accel_days = coll_cfg.get("escalation_acceleration_days", 5)
        max_recs = coll_cfg.get("max_recommendations", 10)

        # Score each overdue invoice
        coll_recs = overdue.copy()
        coll_recs["cash_impact"] = coll_recs["invoice_amount"]
        coll_recs["days_accelerated"] = accel_days

        # Adjust acceleration by customer reliability
        if "payment_score" in coll_recs.columns:
            # Higher payment_score = more likely to respond to escalation
            coll_recs["response_probability"] = coll_recs["payment_score"].fillna(0.5).clip(0.1, 0.95)
        else:
            coll_recs["response_probability"] = 0.5

        # Weighted cash impact
        coll_recs["expected_cash_impact"] = (
            coll_recs["cash_impact"] * coll_recs["response_probability"]
        )

        # Scoring: w1*cash + w2*risk + w3*target + w4*feasibility
        # Normalize each component to 0-1
        max_impact = coll_recs["expected_cash_impact"].max()
        if max_impact > 0:
            coll_recs["score_cash"] = coll_recs["expected_cash_impact"] / max_impact
        else:
            coll_recs["score_cash"] = 0

        max_overdue = coll_recs["days_past_due"].max()
        coll_recs["score_risk"] = (coll_recs["days_past_due"] / max(max_overdue, 1)).clip(0, 1)
        coll_recs["score_target"] = coll_recs["response_probability"]
        coll_recs["score_feasibility"] = 0.8  # escalation is generally feasible

        coll_recs["total_score"] = (
            w1 * coll_recs["score_cash"]
            + w2 * coll_recs["score_risk"]
            + w3 * coll_recs["score_target"]
            + w4 * coll_recs["score_feasibility"]
        ).round(4)

        # Sort and take top N
        coll_recs = coll_recs.sort_values("total_score", ascending=False).head(max_recs)

        # Generate recommendations
        for _, row in coll_recs.iterrows():
            risk = row.get("risk_segment", "MEDIUM")
            if risk == "HIGH":
                action = "Formal notice + phone call"
                channel = "FORMAL"
            elif risk == "MEDIUM":
                action = "Email reminder + follow-up call"
                channel = "REMINDER"
            else:
                action = "Portal nudge + email"
                channel = "REMINDER"

            all_recommendations.append({
                "recommendation_id": str(uuid.uuid4()),
                "lever": "COLLECTIONS",
                "priority": "HIGH" if row["total_score"] > 0.7 else ("MEDIUM" if row["total_score"] > 0.4 else "LOW"),
                "entity_type": "INVOICE",
                "entity_id": row["invoice_id"],
                "customer_id": row["customer_id"],
                "action": action,
                "channel": channel,
                "description": (
                    f"Escalate {row['invoice_id']} (${row['invoice_amount']:,.0f}, "
                    f"{int(row['days_past_due'])} days overdue) — "
                    f"est. accelerate by {accel_days} days, "
                    f"expected cash impact ${row['expected_cash_impact']:,.0f}"
                ),
                "cash_impact": round(float(row["expected_cash_impact"]), 2),
                "days_accelerated": accel_days,
                "risk_segment": risk,
                "score": round(float(row["total_score"]), 4),
                "confidence": row.get("prediction_confidence", "MEDIUM"),
            })

        logger.info("  Generated %d collection recommendations", len(coll_recs))

    # ==================================================================
    # b. VENDOR PAYMENT DEFERRAL LEVER
    # ==================================================================
    defer_cfg = levers.get("vendor_deferral", {})
    s2_preds = input_data.get("s2_predictions", pd.DataFrame())

    if defer_cfg.get("enabled", True) and not s2_preds.empty:
        logger.info("--- Lever: Vendor Payment Deferral ---")

        max_defer = defer_cfg.get("max_deferral_days", 10)
        max_recs = defer_cfg.get("max_recommendations", 5)

        # Use S2 predictions — find payments coming soon that could be deferred
        upcoming = s2_preds.copy()
        upcoming["predicted_payment_date"] = pd.to_datetime(upcoming["predicted_payment_date"])

        # Only payments within next 14 days
        window_end = reference_date + pd.Timedelta(days=14)
        upcoming = upcoming[
            (upcoming["predicted_payment_date"] >= reference_date)
            & (upcoming["predicted_payment_date"] <= window_end)
        ]

        if not upcoming.empty:
            # Score by amount (higher amount = more cash freed)
            upcoming["cash_freed"] = upcoming["expected_payment_amount"]
            max_amt = upcoming["cash_freed"].max()
            upcoming["score"] = (
                w1 * (upcoming["cash_freed"] / max(max_amt, 1))
                + w4 * 0.7  # vendor deferral is moderately feasible
            ).round(4)

            upcoming = upcoming.sort_values("score", ascending=False).head(max_recs)

            for _, row in upcoming.iterrows():
                all_recommendations.append({
                    "recommendation_id": str(uuid.uuid4()),
                    "lever": "VENDOR_DEFERRAL",
                    "priority": "MEDIUM",
                    "entity_type": "BILL",
                    "entity_id": row["transaction_id"],
                    "customer_id": None,
                    "action": f"Defer payment by {max_defer} days (no penalty)",
                    "channel": "TREASURY",
                    "description": (
                        f"Defer {row['transaction_id']} (${row['expected_payment_amount']:,.0f}) "
                        f"by {max_defer} days — improves short-term cash by "
                        f"${row['expected_payment_amount']:,.0f}"
                    ),
                    "cash_impact": round(float(row["expected_payment_amount"]), 2),
                    "days_accelerated": -max_defer,
                    "risk_segment": None,
                    "score": round(float(row["score"]), 4),
                    "confidence": row.get("confidence_tier", "MEDIUM"),
                })

            logger.info("  Generated %d deferral recommendations", len(upcoming))

    # ==================================================================
    # c. EXPENSE DEFERRAL LEVER
    # ==================================================================
    exp_cfg = levers.get("expense_deferral", {})
    if exp_cfg.get("enabled", True):
        logger.info("--- Lever: Expense Deferral ---")

        # Load S6 expense detail
        s6_path = BASE_DIR / "Data" / "forecast_outputs" / "s6_expense_detail.csv"

        if s6_path.exists():
            s6 = pd.read_csv(s6_path)
            eligible_cats = exp_cfg.get("eligible_categories", ["Seasonal", "One-time"])
            max_defer = exp_cfg.get("max_deferral_days", 21)
            max_recs = exp_cfg.get("max_recommendations", 3)

            deferrable = s6[s6["category"].isin(eligible_cats)].copy()
            deferrable["cash_freed"] = deferrable["amount"].abs()
            deferrable = deferrable.sort_values("cash_freed", ascending=False).head(max_recs)

            for _, row in deferrable.iterrows():
                all_recommendations.append({
                    "recommendation_id": str(uuid.uuid4()),
                    "lever": "EXPENSE_DEFERRAL",
                    "priority": "LOW",
                    "entity_type": "EXPENSE",
                    "entity_id": row["expense_id"],
                    "customer_id": None,
                    "action": f"Defer {row['category'].lower()} expense by {max_defer} days",
                    "channel": "FINANCE",
                    "description": (
                        f"Defer {row.get('notes', row['expense_id'])} "
                        f"(${row['cash_freed']:,.0f}) by {max_defer} days — "
                        f"frees ${row['cash_freed']:,.0f} during the period"
                    ),
                    "cash_impact": round(float(row["cash_freed"]), 2),
                    "days_accelerated": -max_defer,
                    "risk_segment": None,
                    "score": round(0.3 + 0.1 * (row["cash_freed"] / max(deferrable["cash_freed"].max(), 1)), 4),
                    "confidence": "LOW",
                })

            logger.info("  Generated %d expense deferral recommendations", len(deferrable))

    # ==================================================================
    # d. RANK ALL RECOMMENDATIONS
    # ==================================================================
    logger.info("--- Final Ranking ---")

    if all_recommendations:
        rec_df = pd.DataFrame(all_recommendations)
        rec_df = rec_df.sort_values("score", ascending=False).reset_index(drop=True)
        rec_df["rank"] = range(1, len(rec_df) + 1)

        # Take top N
        rec_df = rec_df.head(top_n)

        logger.info("  Total recommendations: %d (showing top %d)", len(all_recommendations), len(rec_df))
        logger.info("  By lever: %s", rec_df["lever"].value_counts().to_dict())
        logger.info("  Total cash impact: $%s", f"{rec_df['cash_impact'].sum():,.2f}")

        for _, row in rec_df.iterrows():
            logger.info(
                "  #%d [%s] %s — $%s (score: %.3f)",
                row["rank"], row["lever"], row["entity_id"],
                f"{row['cash_impact']:,.0f}", row["score"],
            )
    else:
        rec_df = pd.DataFrame()
        logger.info("  No recommendations generated")

    logger.info("=" * 60)
    logger.info("RECOMMENDATION ENGINE - COMPLETE")
    logger.info("=" * 60)

    return rec_df


if __name__ == "__main__":
    from steps.recommendation_engine.input_format import run as input_run
    data = input_run()
    recs = run(data)
    print(f"Recommendations: {recs.shape}")
