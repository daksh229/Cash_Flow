"""
S6 Expense Forecast - Forecast Engine
Category-based deterministic scheduling:
  expected_cash_date = obligation_date + payment_lag_days
"""

import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s6.forecast_engine")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s6_expense_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(expenses_df, config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S6 FORECAST ENGINE - START")
    logger.info("=" * 60)

    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    source_module = forecast_cfg.get("source_module", "S6")
    confidence_map = config.get("confidence_mapping", {})

    df = expenses_df.copy()
    logger.info("Input records: %d", len(df))

    if len(df) == 0:
        logger.warning("No expense records to forecast")
        return pd.DataFrame()

    # Apply payment lag
    df["payment_lag_days"] = df["payment_lag_days"].fillna(0).astype(int)
    df["expected_cash_date"] = df["obligation_date"] + pd.to_timedelta(
        df["payment_lag_days"], unit="D"
    )

    # Confidence from category
    df["confidence_tier"] = df["category"].map(confidence_map).fillna("LOW")

    # Build output
    records = []
    for _, row in df.iterrows():
        records.append({
            "forecast_id": str(uuid.uuid4()),
            "expense_id": row["expense_id"],
            "category": row["category"],
            "recurrence_type": row["recurrence_type"],
            "amount": row["amount"],
            "obligation_date": row["obligation_date"].strftime("%Y-%m-%d"),
            "expected_cash_date": row["expected_cash_date"].strftime("%Y-%m-%d"),
            "payment_lag_days": int(row["payment_lag_days"]),
            "confidence_tier": row["confidence_tier"],
            "source_document_ref": row.get("source_document_ref", ""),
            "approved_by": row.get("approved_by", ""),
            "forecast_amount": -abs(row["amount"]),  # negative = outflow
            "source_module": source_module,
            "forecast_type": "EXPENSE",
            "forecast_date": reference_date.strftime("%Y-%m-%d"),
            "notes": row.get("notes", ""),
        })

    output = pd.DataFrame(records)

    total = abs(output["forecast_amount"].sum())
    logger.info("  Total records: %d", len(output))
    logger.info("  Total outflow: $%s", f"{total:,.2f}")
    logger.info("  By category: %s",
                output.groupby("category")["forecast_amount"].sum().abs().round(2).to_dict())
    logger.info("  By confidence: %s",
                output.groupby("confidence_tier")["forecast_amount"].sum().abs().round(2).to_dict())
    logger.info("  By recurrence: %s",
                output.groupby("recurrence_type")["forecast_amount"].sum().abs().round(2).to_dict())

    logger.info("=" * 60)
    logger.info("S6 FORECAST ENGINE - COMPLETE")
    logger.info("=" * 60)

    return output


if __name__ == "__main__":
    from steps.s6_expense_forecast.input_format import run as input_run
    data = input_run()
    forecast = run(data)
    print(f"Forecast: {forecast.shape}")
