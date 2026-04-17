"""
S5 Contingent Inflows - Forecast Engine
Deterministic scheduling: expected_cash_date = expected_receipt_date + hist_receipt_lag
"""

import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s5.forecast_engine")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s5_contingent_inflows.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(inflows_df, config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S5 FORECAST ENGINE - START")
    logger.info("=" * 60)

    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    source_module = forecast_cfg.get("source_module", "S5")
    confidence_map = config.get("confidence_mapping", {})

    df = inflows_df.copy()
    logger.info("Input records: %d", len(df))

    if len(df) == 0:
        logger.warning("No inflow records to forecast")
        return pd.DataFrame()

    # Apply receipt lag
    df["hist_receipt_lag_days"] = df["hist_receipt_lag_days"].fillna(0).astype(int)
    df["expected_cash_date"] = df["expected_receipt_date"] + pd.to_timedelta(
        df["hist_receipt_lag_days"], unit="D"
    )

    # Confidence tier from approval status
    df["confidence_tier"] = df["approval_status"].map(confidence_map).fillna("LOW")

    # Build output
    records = []
    for _, row in df.iterrows():
        records.append({
            "forecast_id": str(uuid.uuid4()),
            "inflow_id": row["inflow_id"],
            "category": row["category"],
            "amount": row["amount"],
            "expected_receipt_date": row["expected_receipt_date"].strftime("%Y-%m-%d"),
            "expected_cash_date": row["expected_cash_date"].strftime("%Y-%m-%d"),
            "receipt_lag_days": int(row["hist_receipt_lag_days"]),
            "approval_status": row["approval_status"],
            "confidence_tier": row["confidence_tier"],
            "source_document_ref": row.get("source_document_ref", ""),
            "forecast_amount": row["amount"],
            "source_module": source_module,
            "forecast_type": "INFLOW",
            "forecast_date": reference_date.strftime("%Y-%m-%d"),
            "notes": row.get("notes", ""),
        })

    output = pd.DataFrame(records)

    total = output["forecast_amount"].sum()
    logger.info("  Total records: %d", len(output))
    logger.info("  Total forecast: $%s", f"{total:,.2f}")
    logger.info("  By category: %s", output.groupby("category")["forecast_amount"].sum().round(2).to_dict())
    logger.info("  By confidence: %s", output.groupby("confidence_tier")["forecast_amount"].sum().round(2).to_dict())

    logger.info("=" * 60)
    logger.info("S5 FORECAST ENGINE - COMPLETE")
    logger.info("=" * 60)

    return output


if __name__ == "__main__":
    from steps.s5_contingent_inflows.input_format import run as input_run
    data = input_run()
    forecast = run(data)
    print(f"Forecast: {forecast.shape}")
