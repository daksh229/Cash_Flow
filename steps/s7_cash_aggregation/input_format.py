"""
S7 Cash Event Normalisation - Input Format
=============================================
Ingests all S1-S6 forecast_outputs into a unified event store.
Step 1 (Ingest) and Step 2 (Standardise) of the S7 pipeline.
"""

import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s7.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
FORECAST_DIR = DATA_DIR / "forecast_outputs"
CONFIG_PATH = BASE_DIR / "config" / "s7_cash_aggregation.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S7 INPUT FORMAT - START")
    logger.info("=" * 60)

    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    horizon_days = forecast_cfg.get("horizon_days", 180)
    horizon_end = reference_date + pd.Timedelta(days=horizon_days)

    input_sources = config.get("input_sources", {})
    forecast_run_id = str(uuid.uuid4())

    # Unified schema columns
    unified_cols = [
        "event_id", "source_module", "forecast_type", "direction",
        "target_date", "forecast_amount", "confidence_tier",
        "forecast_date", "forecast_run_id", "original_file",
    ]

    all_events = []

    # ------------------------------------------------------------------
    # Step 1: Ingest all S1-S6 outputs
    # ------------------------------------------------------------------
    logger.info("Step 1: Ingesting S1-S6 forecast outputs")

    # S1 AR (unified schema)
    for source_key, filename in input_sources.items():
        filepath = FORECAST_DIR / filename
        if not filepath.exists():
            logger.warning("  %s not found: %s — skipping", source_key, filepath)
            continue

        df = pd.read_csv(filepath)
        logger.info("  Loaded %-15s %d records from %s", source_key, len(df), filename)

        # ------------------------------------------------------------------
        # Step 2: Standardise to unified schema
        # ------------------------------------------------------------------
        # Map columns based on source
        if source_key.startswith("s3"):
            # S3 has different columns — map them
            col_map = config.get("s3_column_mapping", {})
            for old_col, new_col in col_map.items():
                if old_col in df.columns and new_col not in df.columns:
                    df[new_col] = df[old_col]

        # Ensure required columns exist
        if "target_date" not in df.columns:
            if "expected_cash_date" in df.columns:
                df["target_date"] = df["expected_cash_date"]
            else:
                logger.warning("  %s has no target_date column — skipping", source_key)
                continue

        if "forecast_amount" not in df.columns:
            logger.warning("  %s has no forecast_amount column — skipping", source_key)
            continue

        if "source_module" not in df.columns:
            df["source_module"] = source_key.upper()

        # Determine direction from amount sign or source
        if "forecast_type" in df.columns:
            df["direction"] = df["forecast_type"].apply(
                lambda x: "OUTFLOW" if x in ["AP", "EXPENSE"] else "INFLOW"
            )
        else:
            df["direction"] = df["forecast_amount"].apply(
                lambda x: "OUTFLOW" if x < 0 else "INFLOW"
            )
            df["forecast_type"] = source_key.upper()

        # Confidence tier
        confidence_map = config.get("confidence_by_source", {})
        if "confidence_tier" not in df.columns:
            src = df["source_module"].iloc[0] if len(df) > 0 else ""
            df["confidence_tier"] = confidence_map.get(src, "LOW")

        # Assign event IDs
        df["event_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
        df["forecast_run_id"] = forecast_run_id
        df["original_file"] = filename
        df["forecast_date"] = df.get("forecast_date", reference_date.strftime("%Y-%m-%d"))

        # Parse target_date and filter to horizon
        df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce")
        df = df.dropna(subset=["target_date"])
        df = df[(df["target_date"] >= reference_date) & (df["target_date"] <= horizon_end)]

        # Select unified columns (keep extras that exist)
        for col in unified_cols:
            if col not in df.columns:
                df[col] = None

        all_events.append(df[unified_cols])

    # Combine all
    if all_events:
        event_store = pd.concat(all_events, ignore_index=True)
    else:
        event_store = pd.DataFrame(columns=unified_cols)

    logger.info("Step 2: Standardised event store: %d total events", len(event_store))
    if len(event_store) > 0:
        logger.info("  By source:")
        for src, count in event_store["source_module"].value_counts().items():
            logger.info("    %-6s %d events", src, count)
        logger.info("  By direction:")
        for d, count in event_store["direction"].value_counts().items():
            logger.info("    %-8s %d events", d, count)

    logger.info("=" * 60)
    logger.info("S7 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return {
        "event_store": event_store,
        "forecast_run_id": forecast_run_id,
    }


if __name__ == "__main__":
    result = run()
    print(f"Event store: {result['event_store'].shape}")
