"""
S4 Sales Pipeline Forecast - Input Format
============================================
Loads CRM pipeline deals, customer features, and historical AR data
for cohort-based milestone extrapolation.
"""

import logging
import yaml
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("s4.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
CONFIG_PATH = BASE_DIR / "config" / "s4_pipeline_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    """
    Load CRM pipeline, customer features, and build historical cohort data.

    Returns
    -------
    dict with 'pipeline', 'customer_delays', 'cohort_stats'
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S4 INPUT FORMAT - START")
    logger.info("=" * 60)

    data_sources = config.get("data_sources", {})

    # ------------------------------------------------------------------
    # 1. Load CRM pipeline
    # ------------------------------------------------------------------
    pipeline_file = data_sources.get("crm_pipeline", "crm_pipeline.csv")
    pipeline = pd.read_csv(DATA_DIR / pipeline_file)
    pipeline["stage_entry_date"] = pd.to_datetime(pipeline["stage_entry_date"])
    pipeline["expected_close_date"] = pd.to_datetime(pipeline["expected_close_date"])

    logger.info("Loaded CRM pipeline: %s", pipeline.shape)
    logger.info("  Deals: %d", len(pipeline))
    logger.info("  Stages: %s", pipeline["crm_stage"].value_counts().to_dict())
    logger.info(
        "  Total pipeline value: $%s",
        f"{pipeline['deal_value'].sum():,.2f}",
    )

    # Exclude Closed Won (already in AR)
    pipeline = pipeline[pipeline["crm_stage"] != "Closed Won"]
    logger.info("  After excluding Closed Won: %d deals", len(pipeline))

    # ------------------------------------------------------------------
    # 2. Load customer payment delays
    # ------------------------------------------------------------------
    cust_file = data_sources.get("customer_features", "features/customer_features.csv")
    cust_features = pd.read_csv(DATA_DIR / cust_file)

    fallback_delay = config.get("payment_delay", {}).get("fallback_days", 30)

    customer_delays = cust_features[["customer_id", "avg_payment_delay"]].copy()
    customer_delays["avg_payment_delay"] = customer_delays[
        "avg_payment_delay"
    ].fillna(fallback_delay).clip(lower=0)

    logger.info("Loaded customer payment delays: %d customers", len(customer_delays))

    # ------------------------------------------------------------------
    # 3. Build cohort stats from historical AR data
    #    (milestone count, billing weights, timing from closed deals)
    # ------------------------------------------------------------------
    logger.info("Building cohort stats from historical AR data")

    invoices = pd.read_csv(DATA_DIR / data_sources.get("invoices", "invoices.csv"))
    payments = pd.read_csv(DATA_DIR / data_sources.get("payments", "payments.csv"))
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"])
    payments["payment_date"] = pd.to_datetime(payments["payment_date"])

    # Get paid AR invoices
    ar_payments = payments[payments["reference_type"] == "AR"]
    paid_invoices = invoices.merge(
        ar_payments[["reference_id", "payment_date", "payment_amount"]],
        left_on="invoice_id", right_on="reference_id", how="inner",
    )

    # Join customer info for segmentation
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    paid_invoices = paid_invoices.merge(
        customers[["customer_id", "industry"]], on="customer_id", how="left"
    )

    # Compute per-customer closed-deal billing stats (proxy for cohort)
    # Count of invoices per customer = proxy for milestone count
    cust_billing = (
        paid_invoices.groupby("customer_id")
        .agg(
            milestone_count=("invoice_id", "count"),
            total_billed=("invoice_amount", "sum"),
            avg_invoice_amount=("invoice_amount", "mean"),
            avg_days_to_pay=("payment_date", lambda x: (x - paid_invoices.loc[x.index, "invoice_date"]).dt.days.mean()),
        )
        .reset_index()
    )

    # Compute global averages for cohort matching
    cohort_stats = {
        "global_milestone_count": int(cust_billing["milestone_count"].median()),
        "global_avg_invoice_amount": float(cust_billing["avg_invoice_amount"].mean()),
        "global_avg_days_to_pay": float(cust_billing["avg_days_to_pay"].mean()),
        "total_closed_deals": len(cust_billing),
    }

    logger.info(
        "  Cohort stats: %d closed customers, avg milestones=%d, avg days_to_pay=%.1f",
        cohort_stats["total_closed_deals"],
        cohort_stats["global_milestone_count"],
        cohort_stats["global_avg_days_to_pay"],
    )

    logger.info("=" * 60)
    logger.info("S4 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return {
        "pipeline": pipeline,
        "customer_delays": customer_delays,
        "cohort_stats": cohort_stats,
    }


if __name__ == "__main__":
    result = run()
    print(f"Pipeline: {result['pipeline'].shape}")
    print(f"Cohort stats: {result['cohort_stats']}")
