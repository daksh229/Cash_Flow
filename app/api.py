"""
Cash Flow Forecasting - FastAPI Backend (Dual Mode)
=====================================================
Two modes per model:
  1. Lookup Mode  - User provides ID, backend fetches features from Feature Store
  2. New Entry    - User provides raw inputs, backend derives features + uses defaults

Endpoints:
  GET  /predict/s1/{invoice_id}       - Lookup: AR Collections
  POST /predict/s1/new                - New: AR Collections
  GET  /predict/s2/{bill_id}          - Lookup: AP Payment
  POST /predict/s2/new                - New: AP Payment
  GET  /predict/credit_risk/{cust_id} - Lookup: Credit Risk
  POST /predict/credit_risk/new       - New: Credit Risk
  GET  /lookup/invoices|bills|customers
  GET  /health | /metrics/{model_key}
"""

import logging
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("api")

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
FEATURE_DIR = BASE_DIR / "Data" / "features"
REPORT_DIR = BASE_DIR / "reports"

REFERENCE_DATE = pd.Timestamp("2026-04-15")

app = FastAPI(
    title="Cash Flow Forecasting API",
    description="Dual-mode: Lookup by ID or New Entry with raw inputs",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Load models
# ---------------------------------------------------------------------------
MODELS = {}


def _load_models():
    model_configs = {
        "s1_ar_prediction": {"primary": "lgbm_model.pkl", "baseline": "rf_model.pkl"},
        "s2_ap_prediction": {"primary": "lgbm_model.pkl", "baseline": "rf_model.pkl"},
        "credit_risk": {"primary": "lgbm_model.pkl", "baseline": "rf_model.pkl"},
    }
    for model_key, files in model_configs.items():
        model_path = MODEL_DIR / model_key
        if not model_path.exists():
            continue
        MODELS[model_key] = {}
        for role, filename in files.items():
            path = model_path / filename
            if path.exists():
                MODELS[model_key][role] = joblib.load(path)
                logger.info("Loaded %s/%s", model_key, role)
    logger.info("Models loaded: %s", list(MODELS.keys()))


_load_models()

# ---------------------------------------------------------------------------
# Load feature tables + compute global defaults
# ---------------------------------------------------------------------------
FEATURE_TABLES = {}
DEFAULTS = {}


def _load_feature_tables():
    tables = [
        "invoice_features", "customer_features", "collections_features",
        "customer_payment_scores", "vendor_features", "bill_features",
    ]
    for name in tables:
        path = FEATURE_DIR / f"{name}.csv"
        if path.exists():
            FEATURE_TABLES[name] = pd.read_csv(path)
            logger.info("Loaded feature table: %-30s %s", name, FEATURE_TABLES[name].shape)

    # Compute global defaults from customers/vendors with history
    cf = FEATURE_TABLES.get("customer_features")
    if cf is not None:
        active = cf[cf["invoice_count"] > 0]
        src = active if len(active) > 50 else cf
        DEFAULTS["customer"] = {
            col: round(float(src[col].mean()), 3)
            for col in src.select_dtypes(include="number").columns
        }
        DEFAULTS["customer"]["seasonality_index"] = 1.0

    vf = FEATURE_TABLES.get("vendor_features")
    if vf is not None:
        active = vf[vf["invoice_count"] > 0]
        src = active if len(active) > 50 else vf
        DEFAULTS["vendor"] = {
            col: round(float(src[col].mean()), 3)
            for col in src.select_dtypes(include="number").columns
        }

    cs = FEATURE_TABLES.get("customer_payment_scores")
    if cs is not None:
        DEFAULTS["scores"] = {
            "payment_score": round(float(cs["payment_score"].mean()), 3),
            "expected_delay": round(float(cs["expected_delay"].mean()), 3),
            "risk_segment": "MEDIUM",
        }

    logger.info("Global defaults computed for new entries")


_load_feature_tables()

# ---------------------------------------------------------------------------
# Feature column definitions (must match training order)
# ---------------------------------------------------------------------------
S1_FEATURES = [
    "invoice_amount", "invoice_age_days", "days_past_due",
    "amount_percentile_customer", "payment_terms_days",
    "dispute_flag", "partial_payment_flag", "partial_payment_amount",
    "avg_payment_delay", "median_payment_delay", "late_payment_ratio",
    "payment_volatility", "dispute_ratio", "ptp_kept_ratio",
    "recent_reminder_velocity", "open_dispute_count",
    "days_since_last_payment", "payment_trend_30d",
    "days_sales_outstanding", "seasonality_index",
    "avg_invoice_amount", "invoice_count",
    "non_invoice_payment_count", "advance_payment_ratio",
    "payment_score", "expected_delay",
    "reminder_count", "call_count", "promise_to_pay_flag",
    "days_since_last_contact", "ptp_kept_ratio_customer",
    "days_until_ptp",
    "invoice_amount_bucket_enc", "risk_segment_enc", "escalation_status_enc",
]

S2_FEATURES = [
    "avg_payment_cycle_days", "payment_volatility", "discount_capture_ratio",
    "late_payment_ratio", "vendor_chase_frequency", "avg_invoice_amount",
    "invoice_count", "po_to_bill_lag", "advance_payment_ratio",
    "bill_age_days", "days_past_due", "bill_amount",
    "amount_percentile_vendor", "early_payment_eligible", "penalty_accruing",
    "bill_amount_bucket_enc", "approval_status_enc",
]

CR_FEATURES = [
    "avg_payment_delay", "median_payment_delay", "late_payment_ratio",
    "payment_volatility", "dispute_ratio", "ptp_kept_ratio",
    "recent_reminder_velocity", "open_dispute_count",
    "days_since_last_payment", "payment_trend_30d",
    "days_sales_outstanding", "seasonality_index",
    "avg_invoice_amount", "invoice_count",
    "non_invoice_payment_count", "advance_payment_ratio",
]

RISK_LABELS = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}
BUCKET_MAP = {"SMALL": 0, "MEDIUM": 1, "LARGE": 2}
RISK_MAP = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
ESC_MAP = {"NONE": 0, "REMINDER": 1, "FORMAL": 2, "LEGAL": 3}
APPROVAL_MAP = {"PENDING": 0, "APPROVED": 1}
TERMS_MAP = {"NET15": 15, "NET30": 30, "NET45": 45, "NET60": 60, "NET90": 90}


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------
class PredictionResponse(BaseModel):
    model: str
    mode: str  # "lookup" or "new_entry"
    prediction: float | str
    baseline_prediction: Optional[float | str] = None
    confidence: Optional[str] = None
    probabilities: Optional[dict] = None
    input_summary: Optional[dict] = None
    details: Optional[dict] = None


# ---------------------------------------------------------------------------
# New Entry request schemas (raw user inputs only)
# ---------------------------------------------------------------------------
class S1NewRequest(BaseModel):
    invoice_amount: float
    invoice_date: str          # YYYY-MM-DD
    due_date: str              # YYYY-MM-DD
    payment_terms: str = "NET30"  # NET15/NET30/NET45/NET60/NET90
    dispute_flag: bool = False
    partial_payment_amount: float = 0.0
    customer_id: Optional[str] = None  # if existing customer, fetch their features


class S2NewRequest(BaseModel):
    bill_amount: float
    bill_date: str             # YYYY-MM-DD
    due_date: str              # YYYY-MM-DD
    approval_status: str = "APPROVED"  # PENDING / APPROVED
    vendor_id: Optional[str] = None  # if existing vendor, fetch their features


class CreditRiskNewRequest(BaseModel):
    avg_payment_delay: float = 0.0
    late_payment_ratio: float = 0.0
    payment_volatility: float = 0.0
    dispute_ratio: float = 0.0
    days_sales_outstanding: float = 30.0
    invoice_count: int = 0
    ptp_kept_ratio: float = 1.0


# ---------------------------------------------------------------------------
# Lookup feature assembly (existing records)
# ---------------------------------------------------------------------------
def _assemble_s1_lookup(invoice_id: str) -> tuple[pd.DataFrame, dict]:
    inv_df = FEATURE_TABLES.get("invoice_features")
    cust_df = FEATURE_TABLES.get("customer_features")
    coll_df = FEATURE_TABLES.get("collections_features")
    scores_df = FEATURE_TABLES.get("customer_payment_scores")

    if inv_df is None:
        raise HTTPException(500, "invoice_features table not loaded")

    row = inv_df[inv_df["invoice_id"] == invoice_id]
    if row.empty:
        raise HTTPException(404, f"Invoice '{invoice_id}' not found in feature store")

    merged = row.copy()
    customer_id = merged["customer_id"].iloc[0]

    if cust_df is not None:
        cust_row = cust_df[cust_df["customer_id"] == customer_id]
        if not cust_row.empty:
            drop_cols = ["customer_id", "feature_date", "feature_version"]
            cust_subset = cust_row.drop(columns=[c for c in drop_cols if c in cust_row.columns])
            merged = pd.concat([merged.reset_index(drop=True), cust_subset.reset_index(drop=True)], axis=1)

    if coll_df is not None:
        coll_row = coll_df[coll_df["invoice_id"] == invoice_id]
        if not coll_row.empty:
            coll_subset = coll_row.drop(columns=["invoice_id"], errors="ignore")
            merged = pd.concat([merged.reset_index(drop=True), coll_subset.reset_index(drop=True)], axis=1)

    if scores_df is not None:
        score_row = scores_df[scores_df["customer_id"] == customer_id]
        if not score_row.empty:
            merged = pd.concat([
                merged.reset_index(drop=True),
                score_row[["payment_score", "expected_delay", "risk_segment"]].reset_index(drop=True),
            ], axis=1)

    merged = _encode_s1(merged)

    raw_info = {
        "invoice_id": invoice_id,
        "customer_id": customer_id,
        "invoice_amount": float(merged["invoice_amount"].iloc[0]),
        "invoice_age_days": int(merged["invoice_age_days"].iloc[0]),
        "days_past_due": int(merged["days_past_due"].iloc[0]),
        "payment_score": float(merged["payment_score"].iloc[0]) if "payment_score" in merged else None,
        "risk_segment": str(merged["risk_segment"].iloc[0]) if "risk_segment" in merged else None,
    }

    return merged[S1_FEATURES], raw_info


def _assemble_s2_lookup(bill_id: str) -> tuple[pd.DataFrame, dict]:
    bill_df = FEATURE_TABLES.get("bill_features")
    vend_df = FEATURE_TABLES.get("vendor_features")

    if bill_df is None:
        raise HTTPException(500, "bill_features table not loaded")

    row = bill_df[bill_df["bill_id"] == bill_id]
    if row.empty:
        raise HTTPException(404, f"Bill '{bill_id}' not found in feature store")

    merged = row.copy()
    vendor_id = merged["vendor_id"].iloc[0]

    if vend_df is not None:
        vend_row = vend_df[vend_df["vendor_id"] == vendor_id]
        if not vend_row.empty:
            drop_cols = ["vendor_id", "feature_date", "feature_version", "last_payment_date"]
            vend_subset = vend_row.drop(columns=[c for c in drop_cols if c in vend_row.columns])
            merged = pd.concat([merged.reset_index(drop=True), vend_subset.reset_index(drop=True)], axis=1)

    merged = _encode_s2(merged)

    raw_info = {
        "bill_id": bill_id,
        "vendor_id": vendor_id,
        "bill_amount": float(merged["bill_amount"].iloc[0]),
        "bill_age_days": int(merged["bill_age_days"].iloc[0]),
        "days_past_due": int(merged["days_past_due"].iloc[0]),
        "approval_status": str(row["approval_status"].iloc[0]) if "approval_status" in row else None,
    }

    return merged[S2_FEATURES], raw_info


def _assemble_cr_lookup(customer_id: str) -> tuple[pd.DataFrame, dict]:
    cust_df = FEATURE_TABLES.get("customer_features")

    if cust_df is None:
        raise HTTPException(500, "customer_features table not loaded")

    row = cust_df[cust_df["customer_id"] == customer_id]
    if row.empty:
        raise HTTPException(404, f"Customer '{customer_id}' not found in feature store")

    merged = row.copy()
    for col in CR_FEATURES:
        if col not in merged.columns:
            merged[col] = 0
    merged = merged.fillna(0)

    raw_info = {
        "customer_id": customer_id,
        "avg_payment_delay": float(merged["avg_payment_delay"].iloc[0]),
        "late_payment_ratio": float(merged["late_payment_ratio"].iloc[0]),
        "payment_volatility": float(merged["payment_volatility"].iloc[0]),
        "dispute_ratio": float(merged["dispute_ratio"].iloc[0]),
        "days_sales_outstanding": float(merged["days_sales_outstanding"].iloc[0]),
        "invoice_count": int(merged["invoice_count"].iloc[0]),
    }

    return merged[CR_FEATURES], raw_info


# ---------------------------------------------------------------------------
# New entry feature assembly (raw inputs -> derived features)
# ---------------------------------------------------------------------------
def _assemble_s1_new(req: S1NewRequest) -> tuple[pd.DataFrame, dict]:
    """Build feature vector for a new invoice from raw inputs."""
    invoice_date = pd.Timestamp(req.invoice_date)
    due_date = pd.Timestamp(req.due_date)

    invoice_age_days = (REFERENCE_DATE - invoice_date).days
    days_past_due = max(0, (REFERENCE_DATE - due_date).days)
    payment_terms_days = TERMS_MAP.get(req.payment_terms, 30)
    partial_payment_flag = 1 if req.partial_payment_amount > 0 else 0

    # If existing customer, fetch their features; otherwise use global defaults
    cust_features = dict(DEFAULTS.get("customer", {}))
    score_features = dict(DEFAULTS.get("scores", {}))
    customer_source = "global_defaults"

    if req.customer_id:
        cust_df = FEATURE_TABLES.get("customer_features")
        scores_df = FEATURE_TABLES.get("customer_payment_scores")

        if cust_df is not None:
            cust_row = cust_df[cust_df["customer_id"] == req.customer_id]
            if not cust_row.empty:
                customer_source = f"feature_store ({req.customer_id})"
                for col in cust_row.select_dtypes(include="number").columns:
                    cust_features[col] = float(cust_row[col].iloc[0])

        if scores_df is not None:
            score_row = scores_df[scores_df["customer_id"] == req.customer_id]
            if not score_row.empty:
                score_features["payment_score"] = float(score_row["payment_score"].iloc[0])
                score_features["expected_delay"] = float(score_row["expected_delay"].iloc[0])
                score_features["risk_segment"] = str(score_row["risk_segment"].iloc[0])

    # Compute amount bucket relative to customer avg
    cust_avg_amt = cust_features.get("avg_invoice_amount", req.invoice_amount)
    if cust_avg_amt > 0:
        if req.invoice_amount <= cust_avg_amt * 0.5:
            bucket = "SMALL"
        elif req.invoice_amount <= cust_avg_amt * 1.5:
            bucket = "MEDIUM"
        else:
            bucket = "LARGE"
        percentile = min(1.0, req.invoice_amount / (cust_avg_amt * 2))
    else:
        bucket = "MEDIUM"
        percentile = 0.5

    risk_segment = score_features.get("risk_segment", "MEDIUM")

    row = {
        "invoice_amount": req.invoice_amount,
        "invoice_age_days": invoice_age_days,
        "days_past_due": days_past_due,
        "amount_percentile_customer": round(percentile, 3),
        "payment_terms_days": payment_terms_days,
        "dispute_flag": int(req.dispute_flag),
        "partial_payment_flag": partial_payment_flag,
        "partial_payment_amount": req.partial_payment_amount,
        # Customer behaviour (from store or defaults)
        "avg_payment_delay": cust_features.get("avg_payment_delay", 0),
        "median_payment_delay": cust_features.get("median_payment_delay", 0),
        "late_payment_ratio": cust_features.get("late_payment_ratio", 0),
        "payment_volatility": cust_features.get("payment_volatility", 0),
        "dispute_ratio": cust_features.get("dispute_ratio", 0),
        "ptp_kept_ratio": cust_features.get("ptp_kept_ratio", 0),
        "recent_reminder_velocity": cust_features.get("recent_reminder_velocity", 0),
        "open_dispute_count": cust_features.get("open_dispute_count", 0),
        "days_since_last_payment": cust_features.get("days_since_last_payment", 0),
        "payment_trend_30d": cust_features.get("payment_trend_30d", 0),
        "days_sales_outstanding": cust_features.get("days_sales_outstanding", 0),
        "seasonality_index": cust_features.get("seasonality_index", 1.0),
        "avg_invoice_amount": cust_features.get("avg_invoice_amount", 0),
        "invoice_count": cust_features.get("invoice_count", 0),
        "non_invoice_payment_count": cust_features.get("non_invoice_payment_count", 0),
        "advance_payment_ratio": cust_features.get("advance_payment_ratio", 0),
        # Scores
        "payment_score": score_features.get("payment_score", 0.5),
        "expected_delay": score_features.get("expected_delay", 0),
        # Collections (new invoice = no collections history)
        "reminder_count": 0,
        "call_count": 0,
        "promise_to_pay_flag": 0,
        "days_since_last_contact": -1,
        "ptp_kept_ratio_customer": cust_features.get("ptp_kept_ratio", 0),
        "days_until_ptp": -1,
        # Encoded
        "invoice_amount_bucket_enc": BUCKET_MAP.get(bucket, 1),
        "risk_segment_enc": RISK_MAP.get(risk_segment, 1),
        "escalation_status_enc": 0,
    }

    df = pd.DataFrame([row])[S1_FEATURES]

    raw_info = {
        "invoice_amount": req.invoice_amount,
        "invoice_date": req.invoice_date,
        "due_date": req.due_date,
        "payment_terms": req.payment_terms,
        "invoice_age_days": invoice_age_days,
        "days_past_due": days_past_due,
        "customer_id": req.customer_id or "NEW (no history)",
        "customer_source": customer_source,
        "risk_segment": risk_segment,
        "payment_score": score_features.get("payment_score", 0.5),
    }

    return df, raw_info


def _assemble_s2_new(req: S2NewRequest) -> tuple[pd.DataFrame, dict]:
    """Build feature vector for a new bill from raw inputs."""
    bill_date = pd.Timestamp(req.bill_date)
    due_date = pd.Timestamp(req.due_date)

    bill_age_days = (REFERENCE_DATE - bill_date).days
    days_past_due = max(0, (REFERENCE_DATE - due_date).days)
    early_payment_eligible = 1 if 0 < (due_date - REFERENCE_DATE).days <= 10 else 0
    penalty_accruing = 1 if days_past_due > 0 and req.approval_status != "PAID" else 0

    # Vendor features: from store or defaults
    vend_features = dict(DEFAULTS.get("vendor", {}))
    vendor_source = "global_defaults"

    if req.vendor_id:
        vend_df = FEATURE_TABLES.get("vendor_features")
        if vend_df is not None:
            vend_row = vend_df[vend_df["vendor_id"] == req.vendor_id]
            if not vend_row.empty:
                vendor_source = f"feature_store ({req.vendor_id})"
                for col in vend_row.select_dtypes(include="number").columns:
                    vend_features[col] = float(vend_row[col].iloc[0])

    # Amount bucket
    vend_avg_amt = vend_features.get("avg_invoice_amount", req.bill_amount)
    if vend_avg_amt > 0:
        if req.bill_amount <= vend_avg_amt * 0.5:
            bucket = "SMALL"
        elif req.bill_amount <= vend_avg_amt * 1.5:
            bucket = "MEDIUM"
        else:
            bucket = "LARGE"
        percentile = min(1.0, req.bill_amount / (vend_avg_amt * 2))
    else:
        bucket = "MEDIUM"
        percentile = 0.5

    row = {
        "avg_payment_cycle_days": vend_features.get("avg_payment_cycle_days", 0),
        "payment_volatility": vend_features.get("payment_volatility", 0),
        "discount_capture_ratio": vend_features.get("discount_capture_ratio", 0),
        "late_payment_ratio": vend_features.get("late_payment_ratio", 0),
        "vendor_chase_frequency": vend_features.get("vendor_chase_frequency", 0),
        "avg_invoice_amount": vend_features.get("avg_invoice_amount", 0),
        "invoice_count": vend_features.get("invoice_count", 0),
        "po_to_bill_lag": vend_features.get("po_to_bill_lag", 0),
        "advance_payment_ratio": vend_features.get("advance_payment_ratio", 0),
        "bill_age_days": bill_age_days,
        "days_past_due": days_past_due,
        "bill_amount": req.bill_amount,
        "amount_percentile_vendor": round(percentile, 3),
        "early_payment_eligible": early_payment_eligible,
        "penalty_accruing": penalty_accruing,
        "bill_amount_bucket_enc": BUCKET_MAP.get(bucket, 1),
        "approval_status_enc": APPROVAL_MAP.get(req.approval_status, 1),
    }

    df = pd.DataFrame([row])[S2_FEATURES]

    raw_info = {
        "bill_amount": req.bill_amount,
        "bill_date": req.bill_date,
        "due_date": req.due_date,
        "bill_age_days": bill_age_days,
        "days_past_due": days_past_due,
        "approval_status": req.approval_status,
        "vendor_id": req.vendor_id or "NEW (no history)",
        "vendor_source": vendor_source,
    }

    return df, raw_info


def _assemble_cr_new(req: CreditRiskNewRequest) -> tuple[pd.DataFrame, dict]:
    """Build feature vector for a new customer from manual inputs."""
    defaults = dict(DEFAULTS.get("customer", {}))

    row = {
        "avg_payment_delay": req.avg_payment_delay,
        "median_payment_delay": req.avg_payment_delay * 0.9,  # estimate
        "late_payment_ratio": req.late_payment_ratio,
        "payment_volatility": req.payment_volatility,
        "dispute_ratio": req.dispute_ratio,
        "ptp_kept_ratio": req.ptp_kept_ratio,
        "recent_reminder_velocity": defaults.get("recent_reminder_velocity", 0),
        "open_dispute_count": 0,
        "days_since_last_payment": defaults.get("days_since_last_payment", 0),
        "payment_trend_30d": 0.0,
        "days_sales_outstanding": req.days_sales_outstanding,
        "seasonality_index": 1.0,
        "avg_invoice_amount": defaults.get("avg_invoice_amount", 0),
        "invoice_count": req.invoice_count,
        "non_invoice_payment_count": 0,
        "advance_payment_ratio": 0.0,
    }

    df = pd.DataFrame([row])[CR_FEATURES]

    raw_info = {
        "customer_id": "NEW (manual entry)",
        "avg_payment_delay": req.avg_payment_delay,
        "late_payment_ratio": req.late_payment_ratio,
        "payment_volatility": req.payment_volatility,
        "dispute_ratio": req.dispute_ratio,
        "days_sales_outstanding": req.days_sales_outstanding,
        "invoice_count": req.invoice_count,
    }

    return df, raw_info


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------
def _encode_s1(merged):
    merged["payment_terms_days"] = merged.get("payment_terms", "NET30").map(TERMS_MAP).fillna(30).astype(int)
    ptp_date = pd.to_datetime(merged.get("promise_to_pay_date"), errors="coerce")
    feat_date = pd.to_datetime(merged.get("feature_date"), errors="coerce")
    if ptp_date.notna().any() and feat_date.notna().any():
        merged["days_until_ptp"] = (ptp_date - feat_date).dt.days
    else:
        merged["days_until_ptp"] = -1
    merged["days_until_ptp"] = merged["days_until_ptp"].fillna(-1).astype(int)
    merged["invoice_amount_bucket_enc"] = merged.get("invoice_amount_bucket", "MEDIUM").map(BUCKET_MAP).fillna(1)
    merged["risk_segment_enc"] = merged.get("risk_segment", "MEDIUM").map(RISK_MAP).fillna(1)
    merged["escalation_status_enc"] = merged.get("escalation_status", "NONE").map(ESC_MAP).fillna(0)
    for col in ["dispute_flag", "partial_payment_flag", "promise_to_pay_flag"]:
        if col in merged.columns:
            merged[col] = merged[col].astype(int)
    for col in S1_FEATURES:
        if col not in merged.columns:
            merged[col] = 0
    return merged.fillna(0)


def _encode_s2(merged):
    merged["bill_amount_bucket_enc"] = merged.get("bill_amount_bucket", "MEDIUM").map(BUCKET_MAP).fillna(1)
    merged["approval_status_enc"] = merged.get("approval_status", "PENDING").map(APPROVAL_MAP).fillna(0)
    for col in ["early_payment_eligible", "penalty_accruing"]:
        if col in merged.columns:
            merged[col] = merged[col].astype(int)
    for col in S2_FEATURES:
        if col not in merged.columns:
            merged[col] = 0
    return merged.fillna(0)


# ---------------------------------------------------------------------------
# Prediction runner
# ---------------------------------------------------------------------------
def _run_prediction(model_key, features_df, mode, raw_info, model_label):
    if model_key not in MODELS:
        raise HTTPException(404, f"Model '{model_key}' not loaded. Train it first.")

    models = MODELS[model_key]
    primary_pred = models["primary"].predict(features_df)[0]
    baseline_pred = None
    if "baseline" in models:
        baseline_pred = models["baseline"].predict(features_df)[0]

    if baseline_pred is not None:
        divergence = abs(float(primary_pred) - float(baseline_pred))
        confidence = "HIGH" if divergence < 3 else ("MEDIUM" if divergence < 7 else "LOW")
    else:
        divergence = None
        confidence = "UNKNOWN"

    return primary_pred, baseline_pred, divergence, confidence


# ---------------------------------------------------------------------------
# Lookup endpoints
# ---------------------------------------------------------------------------
@app.get("/lookup/invoices")
def list_invoices(limit: int = Query(50, ge=1, le=500)):
    inv_df = FEATURE_TABLES.get("invoice_features")
    if inv_df is None:
        raise HTTPException(500, "invoice_features not loaded")
    ids = inv_df["invoice_id"].tolist()[:limit]
    return {"count": len(inv_df), "showing": len(ids), "invoice_ids": ids}


@app.get("/lookup/bills")
def list_bills(limit: int = Query(50, ge=1, le=500)):
    bill_df = FEATURE_TABLES.get("bill_features")
    if bill_df is None:
        raise HTTPException(500, "bill_features not loaded")
    ids = bill_df["bill_id"].tolist()[:limit]
    return {"count": len(bill_df), "showing": len(ids), "bill_ids": ids}


@app.get("/lookup/customers")
def list_customers(limit: int = Query(50, ge=1, le=500)):
    cust_df = FEATURE_TABLES.get("customer_features")
    if cust_df is None:
        raise HTTPException(500, "customer_features not loaded")
    ids = cust_df["customer_id"].tolist()[:limit]
    return {"count": len(cust_df), "showing": len(ids), "customer_ids": ids}


# ---------------------------------------------------------------------------
# Health & metrics
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "models_loaded": list(MODELS.keys()),
        "feature_tables_loaded": list(FEATURE_TABLES.keys()),
    }


@app.get("/metrics/{model_key}")
def get_metrics(model_key: str):
    report_path = REPORT_DIR / model_key / "evaluation_metrics.csv"
    if not report_path.exists():
        raise HTTPException(404, f"Metrics not found for '{model_key}'")
    df = pd.read_csv(report_path)
    return df.set_index("Metric")["Value"].to_dict()


# ---------------------------------------------------------------------------
# S1 endpoints
# ---------------------------------------------------------------------------
@app.get("/predict/s1/{invoice_id}", response_model=PredictionResponse)
def predict_s1_lookup(invoice_id: str):
    """Lookup mode: predict days_to_pay for existing invoice."""
    features_df, raw_info = _assemble_s1_lookup(invoice_id)
    primary, baseline, divergence, confidence = _run_prediction(
        "s1_ar_prediction", features_df, "lookup", raw_info, "S1"
    )
    predicted_days = max(0, round(float(primary), 1))
    return PredictionResponse(
        model="S1 - AR Collections Prediction",
        mode="lookup",
        prediction=predicted_days,
        baseline_prediction=round(float(baseline), 1) if baseline is not None else None,
        confidence=confidence,
        input_summary=raw_info,
        details={
            "predicted_days_to_pay": predicted_days,
            "baseline_days_to_pay": round(float(baseline), 1) if baseline is not None else None,
            "model_divergence": round(divergence, 2) if divergence else None,
            "unit": "days",
        },
    )


@app.post("/predict/s1/new", response_model=PredictionResponse)
def predict_s1_new(request: S1NewRequest):
    """New entry mode: predict days_to_pay from raw invoice inputs."""
    features_df, raw_info = _assemble_s1_new(request)
    primary, baseline, divergence, confidence = _run_prediction(
        "s1_ar_prediction", features_df, "new_entry", raw_info, "S1"
    )
    predicted_days = max(0, round(float(primary), 1))
    return PredictionResponse(
        model="S1 - AR Collections Prediction",
        mode="new_entry",
        prediction=predicted_days,
        baseline_prediction=round(float(baseline), 1) if baseline is not None else None,
        confidence=confidence,
        input_summary=raw_info,
        details={
            "predicted_days_to_pay": predicted_days,
            "baseline_days_to_pay": round(float(baseline), 1) if baseline is not None else None,
            "model_divergence": round(divergence, 2) if divergence else None,
            "unit": "days",
        },
    )


# ---------------------------------------------------------------------------
# S2 endpoints
# ---------------------------------------------------------------------------
@app.get("/predict/s2/{bill_id}", response_model=PredictionResponse)
def predict_s2_lookup(bill_id: str):
    """Lookup mode: predict adjustment_delta for existing bill."""
    features_df, raw_info = _assemble_s2_lookup(bill_id)
    primary, baseline, divergence, confidence = _run_prediction(
        "s2_ap_prediction", features_df, "lookup", raw_info, "S2"
    )
    delta = round(float(primary), 1)
    return PredictionResponse(
        model="S2 - AP Payment Prediction",
        mode="lookup",
        prediction=delta,
        baseline_prediction=round(float(baseline), 1) if baseline is not None else None,
        confidence=confidence,
        input_summary=raw_info,
        details={
            "adjustment_delta_days": delta,
            "direction": "LATER than scheduled" if delta > 0 else "EARLIER than scheduled",
            "model_divergence": round(divergence, 2) if divergence else None,
            "unit": "days",
        },
    )


@app.post("/predict/s2/new", response_model=PredictionResponse)
def predict_s2_new(request: S2NewRequest):
    """New entry mode: predict adjustment_delta from raw bill inputs."""
    features_df, raw_info = _assemble_s2_new(request)
    primary, baseline, divergence, confidence = _run_prediction(
        "s2_ap_prediction", features_df, "new_entry", raw_info, "S2"
    )
    delta = round(float(primary), 1)
    return PredictionResponse(
        model="S2 - AP Payment Prediction",
        mode="new_entry",
        prediction=delta,
        baseline_prediction=round(float(baseline), 1) if baseline is not None else None,
        confidence=confidence,
        input_summary=raw_info,
        details={
            "adjustment_delta_days": delta,
            "direction": "LATER than scheduled" if delta > 0 else "EARLIER than scheduled",
            "model_divergence": round(divergence, 2) if divergence else None,
            "unit": "days",
        },
    )


# ---------------------------------------------------------------------------
# Credit Risk endpoints
# ---------------------------------------------------------------------------
@app.get("/predict/credit_risk/{customer_id}", response_model=PredictionResponse)
def predict_cr_lookup(customer_id: str):
    """Lookup mode: classify existing customer."""
    features_df, raw_info = _assemble_cr_lookup(customer_id)
    return _predict_cr(features_df, raw_info, "lookup")


@app.post("/predict/credit_risk/new", response_model=PredictionResponse)
def predict_cr_new(request: CreditRiskNewRequest):
    """New entry mode: classify new customer from manual inputs."""
    features_df, raw_info = _assemble_cr_new(request)
    return _predict_cr(features_df, raw_info, "new_entry")


def _predict_cr(features_df, raw_info, mode):
    if "credit_risk" not in MODELS:
        raise HTTPException(404, "Credit Risk model not loaded. Train it first.")

    models = MODELS["credit_risk"]
    primary_pred = models["primary"].predict(features_df)[0]
    primary_proba = models["primary"].predict_proba(features_df)[0]

    baseline_pred = None
    if "baseline" in models:
        baseline_pred = models["baseline"].predict(features_df)[0]

    risk_label = RISK_LABELS.get(int(primary_pred), "UNKNOWN")
    baseline_label = RISK_LABELS.get(int(baseline_pred), "UNKNOWN") if baseline_pred is not None else None

    proba_dict = {RISK_LABELS[i]: round(float(p), 4) for i, p in enumerate(primary_proba)}
    max_proba = max(primary_proba)
    confidence = "HIGH" if max_proba >= 0.7 else ("MEDIUM" if max_proba >= 0.5 else "LOW")

    return PredictionResponse(
        model="Credit Risk Assessment",
        mode=mode,
        prediction=risk_label,
        baseline_prediction=baseline_label,
        confidence=confidence,
        probabilities=proba_dict,
        input_summary=raw_info,
        details={
            "risk_segment": risk_label,
            "max_probability": round(float(max_proba), 4),
            "model_agreement": risk_label == baseline_label if baseline_label else None,
        },
    )


# ---------------------------------------------------------------------------
# S3-S7 + RE Forecast data loading (lazy — reloads from disk each access)
# ---------------------------------------------------------------------------
FORECAST_FILES = {
    "s3_wip": "s3_wip_forecast.csv",
    "s4_pipeline": "s4_pipeline_detail.csv",
    "s5_contingent": "s5_contingent_detail.csv",
    "s6_expense": "s6_expense_detail.csv",
    "s7_daily": "s7_daily_position.csv",
    "s7_weekly": "s7_weekly_position.csv",
    "s7_monthly": "s7_monthly_position.csv",
    "s7_events": "s7_event_store.csv",
    "recommendations": "recommendations.csv",
}
FORECAST_DIR = BASE_DIR / "Data" / "forecast_outputs"


def _get_forecast(key: str) -> pd.DataFrame | None:
    """Load a forecast CSV from disk. Returns None if file missing."""
    fname = FORECAST_FILES.get(key)
    if not fname:
        return None
    path = FORECAST_DIR / fname
    if not path.exists():
        return None
    return pd.read_csv(path)


class _ForecastStore(dict):
    """Dict that auto-loads from disk if key is missing but file exists."""

    def get(self, key, default=None):
        val = super().get(key)
        if val is None:
            val = _get_forecast(key)
            if val is not None:
                self[key] = val
        return val if val is not None else default


FORECAST_DATA = _ForecastStore()


def _load_forecast_data():
    """Pre-load all forecast data (called at startup + on reload)."""
    FORECAST_DATA.clear()
    for key, fname in FORECAST_FILES.items():
        path = FORECAST_DIR / fname
        if path.exists():
            FORECAST_DATA[key] = pd.read_csv(path)
            logger.info("Loaded forecast data: %s (%d rows)", key, len(FORECAST_DATA[key]))


_load_forecast_data()


@app.post("/reload")
def reload_data():
    """Reload all forecast data and feature tables from disk."""
    _load_feature_tables()
    _load_forecast_data()
    return {
        "status": "reloaded",
        "feature_tables": list(FEATURE_TABLES.keys()),
        "forecast_data": list(FORECAST_DATA.keys()),
    }


# ---------------------------------------------------------------------------
# S3 Forecast endpoints
# ---------------------------------------------------------------------------
class ForecastResponse(BaseModel):
    model: str
    mode: str
    records: list[dict]
    summary: Optional[dict] = None


@app.get("/lookup/projects")
def list_projects(limit: int = Query(50, ge=1, le=500)):
    """List project IDs available in S3 forecast."""
    df = FORECAST_DATA.get("s3_wip")
    if df is None:
        raise HTTPException(404, "S3 forecast not generated. Run the pipeline first.")
    ids = df["project_id"].unique().tolist()[:limit]
    return {"count": df["project_id"].nunique(), "showing": len(ids), "project_ids": ids}


@app.get("/lookup/deals")
def list_deals(limit: int = Query(50, ge=1, le=500)):
    """List opportunity IDs available in S4 forecast."""
    df = FORECAST_DATA.get("s4_pipeline")
    if df is None:
        raise HTTPException(404, "S4 forecast not generated. Run the pipeline first.")
    ids = df["opportunity_id"].unique().tolist()[:limit]
    return {"count": df["opportunity_id"].nunique(), "showing": len(ids), "opportunity_ids": ids}


@app.get("/forecast/s3/{project_id}")
def forecast_s3_lookup(project_id: str):
    """Get S3 WIP billing forecast for a specific project."""
    df = FORECAST_DATA.get("s3_wip")
    if df is None:
        raise HTTPException(404, "S3 forecast data not loaded.")

    rows = df[df["project_id"] == project_id]
    if rows.empty:
        raise HTTPException(404, f"Project '{project_id}' not found in S3 forecast.")

    records = rows.to_dict("records")
    total = float(rows["forecast_amount"].sum())

    return ForecastResponse(
        model="S3 - WIP Billing Forecast",
        mode="lookup",
        records=records,
        summary={
            "project_id": project_id,
            "customer_id": str(rows["customer_id"].iloc[0]),
            "project_type": str(rows["project_type"].iloc[0]),
            "milestones": len(records),
            "total_forecast": round(total, 2),
            "date_range": f"{rows['expected_cash_date'].min()} to {rows['expected_cash_date'].max()}",
        },
    )


@app.get("/forecast/s3/summary/all")
def forecast_s3_summary():
    """Get full S3 forecast summary."""
    df = FORECAST_DATA.get("s3_wip")
    if df is None:
        raise HTTPException(404, "S3 forecast data not loaded.")

    summary = {
        "total_milestones": len(df),
        "total_projects": int(df["project_id"].nunique()),
        "total_customers": int(df["customer_id"].nunique()),
        "total_forecast": round(float(df["forecast_amount"].sum()), 2),
        "by_confidence": df.groupby("confidence_tier")["forecast_amount"].sum().round(2).to_dict(),
        "by_project_type": df.groupby("project_type")["forecast_amount"].sum().round(2).to_dict(),
    }
    return summary


@app.get("/forecast/s4/{opportunity_id}")
def forecast_s4_lookup(opportunity_id: str):
    """Get S4 pipeline forecast for a specific deal."""
    df = FORECAST_DATA.get("s4_pipeline")
    if df is None:
        raise HTTPException(404, "S4 forecast data not loaded.")

    rows = df[df["opportunity_id"] == opportunity_id]
    if rows.empty:
        raise HTTPException(404, f"Deal '{opportunity_id}' not found in S4 forecast.")

    records = rows.to_dict("records")
    total = float(rows["forecast_amount"].sum())

    return ForecastResponse(
        model="S4 - Sales Pipeline Forecast",
        mode="lookup",
        records=records,
        summary={
            "opportunity_id": opportunity_id,
            "customer_id": str(rows["customer_id"].iloc[0]),
            "deal_value": float(rows["deal_value"].iloc[0]),
            "crm_stage": str(rows["crm_stage"].iloc[0]),
            "stage_probability": float(rows["stage_probability"].iloc[0]),
            "milestones": len(records),
            "total_weighted_forecast": round(total, 2),
            "date_range": f"{rows['expected_cash_date'].min()} to {rows['expected_cash_date'].max()}",
        },
    )


@app.get("/forecast/s4/summary/all")
def forecast_s4_summary():
    """Get full S4 forecast summary."""
    df = FORECAST_DATA.get("s4_pipeline")
    if df is None:
        raise HTTPException(404, "S4 forecast data not loaded.")

    summary = {
        "total_records": len(df),
        "total_deals": int(df["opportunity_id"].nunique()),
        "total_customers": int(df["customer_id"].nunique()),
        "total_forecast": round(float(df["forecast_amount"].sum()), 2),
        "by_stage": df.groupby("crm_stage")["forecast_amount"].sum().round(2).to_dict(),
        "by_deal_type": df.groupby("deal_type")["forecast_amount"].sum().round(2).to_dict(),
    }
    return summary


@app.get("/forecast/s3/summary/report")
def forecast_s3_report():
    """Get S3 summary metrics from report file."""
    path = REPORT_DIR / "s3_wip_forecast" / "forecast_summary.csv"
    if not path.exists():
        raise HTTPException(404, "S3 report not found.")
    df = pd.read_csv(path)
    return df.set_index("Metric")["Value"].to_dict()


@app.get("/forecast/s4/summary/report")
def forecast_s4_report():
    """Get S4 summary metrics from report file."""
    path = REPORT_DIR / "s4_pipeline_forecast" / "forecast_summary.csv"
    if not path.exists():
        raise HTTPException(404, "S4 report not found.")
    df = pd.read_csv(path)
    return df.set_index("Metric")["Value"].to_dict()


# ---------------------------------------------------------------------------
# S5 Contingent Inflows endpoints
# ---------------------------------------------------------------------------
@app.get("/forecast/s5/summary/all")
def forecast_s5_summary():
    df = FORECAST_DATA.get("s5_contingent")
    if df is None:
        raise HTTPException(404, "S5 forecast not generated. Run the pipeline first.")
    summary = {
        "total_records": len(df),
        "total_forecast": round(float(df["forecast_amount"].sum()), 2),
        "by_category": df.groupby("category")["forecast_amount"].sum().round(2).to_dict(),
        "by_confidence": df.groupby("confidence_tier")["forecast_amount"].sum().round(2).to_dict(),
        "by_approval": df.groupby("approval_status")["forecast_amount"].sum().round(2).to_dict(),
    }
    return summary


@app.get("/forecast/s5/records")
def forecast_s5_records():
    df = FORECAST_DATA.get("s5_contingent")
    if df is None:
        raise HTTPException(404, "S5 forecast not generated.")
    return df.to_dict("records")


@app.get("/forecast/s5/summary/report")
def forecast_s5_report():
    path = REPORT_DIR / "s5_contingent_inflows" / "forecast_summary.csv"
    if not path.exists():
        raise HTTPException(404, "S5 report not found.")
    df = pd.read_csv(path)
    return df.set_index("Metric")["Value"].to_dict()


# ---------------------------------------------------------------------------
# S6 Expense Forecast endpoints
# ---------------------------------------------------------------------------
@app.get("/forecast/s6/summary/all")
def forecast_s6_summary():
    df = FORECAST_DATA.get("s6_expense")
    if df is None:
        raise HTTPException(404, "S6 forecast not generated. Run the pipeline first.")
    summary = {
        "total_records": len(df),
        "total_outflow": round(abs(float(df["forecast_amount"].sum())), 2),
        "by_category": df.groupby("category")["forecast_amount"].sum().abs().round(2).to_dict(),
        "by_recurrence": df.groupby("recurrence_type")["forecast_amount"].sum().abs().round(2).to_dict(),
        "by_confidence": df.groupby("confidence_tier")["forecast_amount"].sum().abs().round(2).to_dict(),
    }
    return summary


@app.get("/forecast/s6/records")
def forecast_s6_records():
    df = FORECAST_DATA.get("s6_expense")
    if df is None:
        raise HTTPException(404, "S6 forecast not generated.")
    return df.to_dict("records")


@app.get("/forecast/s6/summary/report")
def forecast_s6_report():
    path = REPORT_DIR / "s6_expense_forecast" / "forecast_summary.csv"
    if not path.exists():
        raise HTTPException(404, "S6 report not found.")
    df = pd.read_csv(path)
    return df.set_index("Metric")["Value"].to_dict()


# ---------------------------------------------------------------------------
# S7 Cash Aggregation endpoints
# ---------------------------------------------------------------------------
@app.get("/forecast/s7/daily")
def forecast_s7_daily():
    df = FORECAST_DATA.get("s7_daily")
    if df is None:
        raise HTTPException(404, "S7 daily position not generated.")
    return df.to_dict("records")


@app.get("/forecast/s7/weekly")
def forecast_s7_weekly():
    df = FORECAST_DATA.get("s7_weekly")
    if df is None:
        raise HTTPException(404, "S7 weekly position not generated.")
    return df.to_dict("records")


@app.get("/forecast/s7/monthly")
def forecast_s7_monthly():
    df = FORECAST_DATA.get("s7_monthly")
    if df is None:
        raise HTTPException(404, "S7 monthly position not generated.")
    return df.to_dict("records")


@app.get("/forecast/s7/summary")
def forecast_s7_summary():
    daily = FORECAST_DATA.get("s7_daily")
    events = FORECAST_DATA.get("s7_events")
    if daily is None:
        raise HTTPException(404, "S7 data not generated. Run the pipeline first.")

    summary = {
        "total_days": len(daily),
        "total_inflows": round(float(daily["gross_inflow"].sum()), 2),
        "total_outflows": round(float(daily["gross_outflow"].sum()), 2),
        "net_change": round(float(daily["net_flow"].sum()), 2),
        "closing_balance": round(float(daily["cumulative_position"].iloc[-1]), 2),
        "min_position": round(float(daily["cumulative_position"].min()), 2),
    }

    if events is not None:
        summary["total_events"] = len(events)
        suppressed = events["suppressed"].sum() if "suppressed" in events.columns else 0
        summary["active_events"] = len(events) - int(suppressed)
        summary["suppressed_events"] = int(suppressed)
        if "source_module" in events.columns:
            summary["by_source"] = (
                events[events.get("suppressed", False) == False]
                .groupby("source_module")["forecast_amount"]
                .agg(["count", "sum"])
                .round(2)
                .rename(columns={"count": "events", "sum": "total"})
                .to_dict("index")
            )

    return summary


@app.get("/forecast/s7/summary/report")
def forecast_s7_report():
    path = REPORT_DIR / "s7_cash_aggregation" / "cash_forecast_summary.csv"
    if not path.exists():
        raise HTTPException(404, "S7 report not found.")
    df = pd.read_csv(path)
    return df.set_index("Metric")["Value"].to_dict()


# ---------------------------------------------------------------------------
# Recommendation Engine endpoints
# ---------------------------------------------------------------------------
@app.get("/recommendations")
def get_recommendations():
    df = FORECAST_DATA.get("recommendations")
    if df is None:
        raise HTTPException(404, "Recommendations not generated. Run the pipeline first.")
    return df.to_dict("records")


@app.get("/recommendations/summary")
def recommendations_summary():
    df = FORECAST_DATA.get("recommendations")
    if df is None:
        raise HTTPException(404, "Recommendations not generated.")
    summary = {
        "total": len(df),
        "total_cash_impact": round(float(df["cash_impact"].sum()), 2),
        "by_lever": df.groupby("lever").agg(
            count=("recommendation_id", "count"),
            cash_impact=("cash_impact", "sum"),
        ).round(2).to_dict("index"),
        "by_priority": df["priority"].value_counts().to_dict(),
    }
    return summary


@app.get("/recommendations/report")
def recommendations_report():
    path = REPORT_DIR / "recommendation_engine" / "recommendation_summary.csv"
    if not path.exists():
        raise HTTPException(404, "RE report not found.")
    df = pd.read_csv(path)
    return df.set_index("Metric")["Value"].to_dict()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
