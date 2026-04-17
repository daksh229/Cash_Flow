"""
S4 Sales Pipeline Forecast - Forecast Engine
===============================================
Rule-based cohort matching with deterministic arithmetic (Phase 1).

Two parts:
  Part 1 - Milestone extrapolation (when CRM has no milestone dates)
            Uses historical AR data to infer milestone count, billing split, timing
  Part 2 - Probability weighting
            forecasted_amount = deal_value x stage_probability x milestone_weight
"""

import logging
import yaml
import uuid
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("s4.forecast_engine")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s4_pipeline_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(input_data, config=None):
    """
    Apply pipeline forecast rules to each deal.

    Parameters
    ----------
    input_data : dict
        Output from input_format.run() with 'pipeline', 'customer_delays', 'cohort_stats'
    config : dict or None

    Returns
    -------
    pd.DataFrame : forecast records at opportunity-milestone level
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S4 FORECAST ENGINE - START")
    logger.info("=" * 60)

    pipeline = input_data["pipeline"]
    customer_delays = input_data["customer_delays"]
    cohort_stats = input_data["cohort_stats"]

    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    horizon_days = forecast_cfg.get("horizon_days", 180)
    source_module = forecast_cfg.get("source_module", "S4")
    forecast_type = forecast_cfg.get("forecast_type", "PIPELINE")

    cohort_cfg = config.get("cohort", {})
    fallback_ms_count = cohort_cfg.get("fallback_milestone_count", 3)
    fallback_weights = cohort_cfg.get("fallback_billing_weights", [0.30, 0.40, 0.30])
    fallback_timing = cohort_cfg.get("fallback_timing_days", [0, 30, 60])

    stage_probs = config.get("stage_probabilities", {})
    invoice_lag = config.get("invoice_lag", {}).get("default_days", 7)
    fallback_delay = config.get("payment_delay", {}).get("fallback_days", 30)

    horizon_end = reference_date + pd.Timedelta(days=horizon_days)

    logger.info("Input deals: %d", len(pipeline))
    logger.info("Horizon: %s to %s (%d days)", reference_date.date(), horizon_end.date(), horizon_days)

    # Merge customer payment delays
    pipeline = pipeline.merge(customer_delays, on="customer_id", how="left")
    pipeline["avg_payment_delay"] = pipeline["avg_payment_delay"].fillna(
        fallback_delay
    ).clip(lower=0)

    forecast_records = []

    for _, deal in pipeline.iterrows():
        opp_id = deal["opportunity_id"]
        deal_value = deal["deal_value"]
        stage = deal["crm_stage"]
        close_date = deal["expected_close_date"]
        cust_delay = deal["avg_payment_delay"]
        has_milestones = deal.get("has_explicit_milestones", False)

        # Stage probability (from config or deal-level)
        stage_prob = stage_probs.get(stage, deal.get("stage_probability", 0.5))

        # ---------------------------------------------------------------
        # Part 1: Milestone extrapolation
        # ---------------------------------------------------------------
        milestone_count = fallback_ms_count
        billing_weights = fallback_weights[:milestone_count]
        milestone_timing = fallback_timing[:milestone_count]

        # Normalize weights to sum to 1
        weight_sum = sum(billing_weights)
        if weight_sum > 0:
            billing_weights = [w / weight_sum for w in billing_weights]

        # ---------------------------------------------------------------
        # Part 2: Probability weighting per milestone
        # ---------------------------------------------------------------
        for ms_idx in range(milestone_count):
            milestone_weight = billing_weights[ms_idx]
            timing_days = milestone_timing[ms_idx]

            # forecasted_amount = deal_value x stage_probability x milestone_weight
            forecasted_amount = round(deal_value * stage_prob * milestone_weight, 2)

            # Expected dates
            milestone_date = close_date + pd.Timedelta(days=timing_days)
            expected_invoice_date = milestone_date + pd.Timedelta(days=invoice_lag)
            expected_cash_date = expected_invoice_date + pd.Timedelta(
                days=int(cust_delay)
            )

            # Skip if outside forecast horizon
            if expected_cash_date > horizon_end or expected_cash_date < reference_date:
                continue

            # Confidence tier based on stage
            if stage_prob >= 0.75:
                confidence = "MEDIUM"
            elif stage_prob >= 0.50:
                confidence = "LOW"
            else:
                confidence = "LOW"

            forecast_records.append({
                "forecast_id": str(uuid.uuid4()),
                "opportunity_id": opp_id,
                "customer_id": deal["customer_id"],
                "deal_value": deal_value,
                "deal_type": deal.get("deal_type", ""),
                "deal_size_band": deal.get("deal_size_band", ""),
                "crm_stage": stage,
                "stage_probability": stage_prob,
                "milestone_sequence": ms_idx + 1,
                "milestone_weight": round(milestone_weight, 3),
                "forecast_amount": forecasted_amount,
                "expected_close_date": close_date.strftime("%Y-%m-%d"),
                "expected_invoice_date": expected_invoice_date.strftime("%Y-%m-%d"),
                "expected_cash_date": expected_cash_date.strftime("%Y-%m-%d"),
                "invoice_lag_days": invoice_lag,
                "customer_payment_delay_days": int(cust_delay),
                "confidence_tier": confidence,
                "source_module": source_module,
                "forecast_type": forecast_type,
                "forecast_date": reference_date.strftime("%Y-%m-%d"),
            })

    output = pd.DataFrame(forecast_records)

    if len(output) > 0:
        total_forecast = output["forecast_amount"].sum()
        logger.info("  Total milestone records: %d", len(output))
        logger.info("  Deals covered: %d", output["opportunity_id"].nunique())
        logger.info("  Customers covered: %d", output["customer_id"].nunique())
        logger.info("  Total weighted forecast: $%s", f"{total_forecast:,.2f}")
        logger.info(
            "  By stage: %s",
            output.groupby("crm_stage")["forecast_amount"]
            .sum()
            .round(2)
            .to_dict(),
        )
        logger.info(
            "  Date range: %s to %s",
            output["expected_cash_date"].min(),
            output["expected_cash_date"].max(),
        )
    else:
        logger.warning("  No forecast records generated")

    logger.info("=" * 60)
    logger.info("S4 FORECAST ENGINE - COMPLETE")
    logger.info("=" * 60)

    return output


if __name__ == "__main__":
    from steps.s4_pipeline_forecast.input_format import run as input_run

    data = input_run()
    forecast = run(data)
    print(f"\nForecast shape: {forecast.shape}")
