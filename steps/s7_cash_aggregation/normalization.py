"""
S7 - Event Normalisation
========================
Harmonises the heterogeneous S1..S6 outputs into a single canonical
schema so S7 aggregation, dedup, and trust scoring can operate on a
uniform row shape.

Canonical event schema:
    event_id       str   stable hash across re-runs
    source_model   str   s1..s6
    entity_id      str   customer/vendor/project/deal id
    event_date     date  expected cash movement date
    amount         float signed: inflow +, outflow -
    direction      str   "inflow" | "outflow"
    confidence     float 0..1
    currency       str   ISO-4217 code (default INR)
    raw            dict  original row for traceability
"""

import hashlib
import logging
import pandas as pd

logger = logging.getLogger(__name__)

CANONICAL_COLUMNS = [
    "event_id", "source_model", "entity_id", "event_date",
    "amount", "direction", "confidence", "currency", "raw",
]

SOURCE_FIELD_MAP = {
    "s1_ar_prediction":      {"date": "predicted_payment_date", "amount": "amount",          "entity": "customer_id"},
    "s2_ap_prediction":      {"date": "predicted_payment_date", "amount": "amount",          "entity": "vendor_id",   "sign": -1},
    "s3_wip_forecast":       {"date": "expected_cash_date",     "amount": "forecast_amount", "entity": "project_id"},
    "s4_pipeline_forecast":  {"date": "expected_cash_date",     "amount": "weighted_amount", "entity": "deal_id"},
    "s5_contingent_inflows": {"date": "expected_receipt_date",  "amount": "amount",          "entity": "source_id"},
    "s6_expense_forecast":   {"date": "scheduled_date",         "amount": "amount",          "entity": "expense_id",  "sign": -1},
}


def _make_event_id(source, entity, date, amount) -> str:
    raw = f"{source}|{entity}|{date}|{round(float(amount), 2)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def normalise(df: pd.DataFrame, source_model: str, default_currency="INR") -> pd.DataFrame:
    mapping = SOURCE_FIELD_MAP.get(source_model)
    if not mapping:
        raise ValueError(f"No normalisation map for source '{source_model}'")

    if df is None or df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    sign = mapping.get("sign", 1)
    out = pd.DataFrame({
        "event_date":  pd.to_datetime(df[mapping["date"]], errors="coerce"),
        "amount":      df[mapping["amount"]].astype(float) * sign,
        "entity_id":   df[mapping["entity"]].astype(str),
        "confidence":  df.get("confidence", pd.Series([0.7] * len(df))).astype(float),
        "currency":    df.get("currency", pd.Series([default_currency] * len(df))),
    })
    out["source_model"] = source_model
    out["direction"] = out["amount"].apply(lambda x: "inflow" if x >= 0 else "outflow")
    out["event_id"] = [
        _make_event_id(source_model, e, d, a)
        for e, d, a in zip(out["entity_id"], out["event_date"], out["amount"])
    ]
    out["raw"] = df.to_dict(orient="records")

    before = len(out)
    out = out.dropna(subset=["event_date"])
    if len(out) != before:
        logger.warning("normalise[%s] dropped %d rows with invalid dates",
                       source_model, before - len(out))

    return out[CANONICAL_COLUMNS]


def normalise_all(module_outputs: dict) -> pd.DataFrame:
    """module_outputs: {source_model: DataFrame}"""
    frames = [normalise(df, src) for src, df in module_outputs.items() if df is not None]
    if not frames:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    return pd.concat(frames, ignore_index=True)
