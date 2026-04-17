"""
Feature Table Generation - Common Step
=======================================
Reads raw data from Data/ and computes all 6 feature tables:
  1. customer_features
  2. customer_payment_scores
  3. invoice_features
  4. collections_features
  5. vendor_features
  6. bill_features

Outputs are saved to Data/features/ for consumption by all prediction models.
"""

import os
import logging
import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("feature_table")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "Data"
FEATURE_DIR = DATA_DIR / "features"

REFERENCE_DATE = pd.Timestamp("2026-04-15")  # snapshot date matching sample_data


def _load_raw_tables():
    """Load all 8 raw tables from Data/."""
    logger.info("Loading raw tables from %s", DATA_DIR)
    tables = {
        "customers": pd.read_csv(DATA_DIR / "customers.csv"),
        "invoices": pd.read_csv(DATA_DIR / "invoices.csv"),
        "payments": pd.read_csv(DATA_DIR / "payments.csv"),
        "collections_events": pd.read_csv(DATA_DIR / "collections_events.csv"),
        "non_invoice_payments": pd.read_csv(DATA_DIR / "non_invoice_payments.csv"),
        "vendors": pd.read_csv(DATA_DIR / "vendors.csv"),
        "bills": pd.read_csv(DATA_DIR / "bills.csv"),
        "purchase_orders": pd.read_csv(DATA_DIR / "purchase_orders.csv"),
    }
    # Parse dates
    date_cols = {
        "invoices": ["invoice_date", "due_date"],
        "payments": ["payment_date"],
        "collections_events": ["event_date", "promise_to_pay_date"],
        "non_invoice_payments": ["payment_date"],
        "bills": ["bill_date", "due_date"],
        "purchase_orders": ["po_date", "expected_invoice_date"],
    }
    for tbl, cols in date_cols.items():
        for col in cols:
            tables[tbl][col] = pd.to_datetime(tables[tbl][col], errors="coerce")

    for name, df in tables.items():
        logger.info("  %-25s shape=%s", name, df.shape)
    return tables


# ===================================================================
# 1. CUSTOMER FEATURES
# ===================================================================
def build_customer_features(tables):
    """Build customer_features from invoices, payments, collections_events, non_invoice_payments."""
    logger.info("--- Building customer_features ---")

    invoices = tables["invoices"].copy()
    payments = tables["payments"].copy()
    collections = tables["collections_events"].copy()
    non_inv_pay = tables["non_invoice_payments"].copy()

    # --- Join AR payments to invoices ---
    ar_payments = payments[payments["reference_type"] == "AR"].copy()
    inv_pay = invoices.merge(
        ar_payments[["reference_id", "payment_date", "payment_amount"]],
        left_on="invoice_id",
        right_on="reference_id",
        how="left",
    )

    # days_to_pay for paid invoices
    inv_pay["days_to_pay"] = (
        inv_pay["payment_date"] - inv_pay["invoice_date"]
    ).dt.days
    inv_pay["days_late"] = (
        inv_pay["payment_date"] - inv_pay["due_date"]
    ).dt.days

    # --- Per-customer aggregation from paid invoices ---
    paid = inv_pay.dropna(subset=["payment_date"])
    cust_pay_stats = (
        paid.groupby("customer_id")
        .agg(
            avg_payment_delay=("days_late", "mean"),
            median_payment_delay=("days_late", "median"),
            late_payment_ratio=("days_late", lambda x: (x > 0).mean()),
            payment_volatility=("days_to_pay", "std"),
            avg_invoice_amount=("invoice_amount", "mean"),
            invoice_count=("invoice_id", "nunique"),
        )
        .reset_index()
    )
    cust_pay_stats["payment_volatility"] = cust_pay_stats["payment_volatility"].fillna(0)

    # --- Dispute ratio from all invoices ---
    dispute_stats = (
        invoices.groupby("customer_id")
        .agg(dispute_ratio=("dispute_flag", "mean"))
        .reset_index()
    )

    # --- Collections-based features per customer ---
    # PTP kept ratio
    ptp_events = collections[collections["event_type"] == "PTP"].copy()
    ptp_events = ptp_events.merge(
        ar_payments[["reference_id", "payment_date"]],
        left_on="invoice_id",
        right_on="reference_id",
        how="left",
    )
    ptp_events["ptp_kept"] = (
        ptp_events["payment_date"] <= ptp_events["promise_to_pay_date"]
    ).astype(float)

    ptp_ratio = (
        ptp_events.groupby("customer_id")
        .agg(ptp_kept_ratio=("ptp_kept", "mean"))
        .reset_index()
    )

    # Recent reminder velocity: reminders in last 14 days
    recent_cutoff = REFERENCE_DATE - pd.Timedelta(days=14)
    recent_reminders = collections[
        (collections["event_type"] == "REMINDER")
        & (collections["event_date"] >= recent_cutoff)
    ]
    reminder_vel = (
        recent_reminders.groupby("customer_id")
        .size()
        .reset_index(name="recent_reminder_velocity")
    )

    # Open dispute count
    open_disputes = invoices[invoices["dispute_flag"] == True]
    dispute_count = (
        open_disputes.groupby("customer_id")
        .size()
        .reset_index(name="open_dispute_count")
    )

    # Days since last payment
    last_pay = (
        paid.groupby("customer_id")["payment_date"]
        .max()
        .reset_index()
    )
    last_pay["days_since_last_payment"] = (
        REFERENCE_DATE - last_pay["payment_date"]
    ).dt.days
    last_pay = last_pay[["customer_id", "days_since_last_payment"]]

    # Payment trend 30d
    recent_30 = paid[paid["payment_date"] >= (REFERENCE_DATE - pd.Timedelta(days=30))]
    recent_avg = (
        recent_30.groupby("customer_id")["days_to_pay"]
        .mean()
        .reset_index(name="recent_avg_dtp")
    )
    overall_avg = (
        paid.groupby("customer_id")["days_to_pay"]
        .mean()
        .reset_index(name="overall_avg_dtp")
    )
    trend = recent_avg.merge(overall_avg, on="customer_id", how="left")
    trend["payment_trend_30d"] = trend["recent_avg_dtp"] - trend["overall_avg_dtp"]
    trend = trend[["customer_id", "payment_trend_30d"]]

    # DSO: outstanding AR / (total revenue / 365)
    open_ar = invoices[invoices["invoice_status"].isin(["OPEN", "PARTIAL", "DISPUTED"])]
    outstanding = (
        open_ar.groupby("customer_id")["invoice_amount"]
        .sum()
        .reset_index(name="outstanding_ar")
    )
    total_revenue = (
        invoices.groupby("customer_id")["invoice_amount"]
        .sum()
        .reset_index(name="total_revenue")
    )
    dso = outstanding.merge(total_revenue, on="customer_id", how="left")
    dso["days_sales_outstanding"] = np.where(
        dso["total_revenue"] > 0,
        dso["outstanding_ar"] / (dso["total_revenue"] / 365),
        0,
    )
    dso = dso[["customer_id", "days_sales_outstanding"]]

    # Seasonality index
    paid_copy = paid.copy()
    paid_copy["pay_month"] = paid_copy["payment_date"].dt.month
    month_avg = paid_copy.groupby(["customer_id", "pay_month"])["days_to_pay"].mean()
    cust_avg = paid_copy.groupby("customer_id")["days_to_pay"].mean()
    seasonality = (month_avg / cust_avg).groupby("customer_id").std().reset_index(name="seasonality_index")
    seasonality["seasonality_index"] = seasonality["seasonality_index"].fillna(1.0)
    seasonality["seasonality_index"] = 1.0 + (
        seasonality["seasonality_index"] - seasonality["seasonality_index"].mean()
    )
    seasonality["seasonality_index"] = seasonality["seasonality_index"].clip(0.5, 2.0)

    # Non-invoice payment features
    cust_nip = non_inv_pay[non_inv_pay["party_type"] == "CUSTOMER"]
    nip_count = (
        cust_nip.groupby("party_id")
        .size()
        .reset_index(name="non_invoice_payment_count")
    )
    nip_count = nip_count.rename(columns={"party_id": "customer_id"})

    advance_nip = cust_nip[cust_nip["payment_type"] == "ADVANCE"]
    advance_amt = (
        advance_nip.groupby("party_id")["amount"]
        .sum()
        .reset_index(name="advance_amount")
    )
    advance_amt = advance_amt.rename(columns={"party_id": "customer_id"})

    total_cust_pay = (
        paid.groupby("customer_id")["payment_amount"]
        .sum()
        .reset_index(name="total_pay_amount")
    )
    adv_ratio = advance_amt.merge(total_cust_pay, on="customer_id", how="left")
    adv_ratio["advance_payment_ratio"] = np.where(
        adv_ratio["total_pay_amount"] > 0,
        adv_ratio["advance_amount"] / adv_ratio["total_pay_amount"],
        0,
    )
    adv_ratio = adv_ratio[["customer_id", "advance_payment_ratio"]]

    # --- Merge everything ---
    cf = tables["customers"][["customer_id"]].copy()
    for df in [
        cust_pay_stats, dispute_stats, ptp_ratio, reminder_vel,
        dispute_count, last_pay, trend, dso, seasonality,
        nip_count, adv_ratio,
    ]:
        cf = cf.merge(df, on="customer_id", how="left")

    # Fill defaults
    fill_zero = [
        "avg_payment_delay", "median_payment_delay", "late_payment_ratio",
        "payment_volatility", "dispute_ratio", "ptp_kept_ratio",
        "recent_reminder_velocity", "open_dispute_count", "days_since_last_payment",
        "payment_trend_30d", "days_sales_outstanding", "avg_invoice_amount",
        "invoice_count", "non_invoice_payment_count", "advance_payment_ratio",
    ]
    for col in fill_zero:
        if col in cf.columns:
            cf[col] = cf[col].fillna(0)

    cf["seasonality_index"] = cf["seasonality_index"].fillna(1.0)
    cf["feature_date"] = REFERENCE_DATE.strftime("%Y-%m-%d")
    cf["feature_version"] = "v1.0.0"

    logger.info("  customer_features shape: %s", cf.shape)
    return cf


# ===================================================================
# 2. CUSTOMER PAYMENT SCORES
# ===================================================================
def build_customer_payment_scores(customer_features):
    """Derive customer_payment_scores from customer_features using rule-based scoring."""
    logger.info("--- Building customer_payment_scores ---")

    cf = customer_features.copy()

    # Payment score: composite reliability index (0-1, higher = better)
    cf["_late_score"] = 1.0 - cf["late_payment_ratio"].clip(0, 1)
    vol_q95 = max(cf["payment_volatility"].quantile(0.95), 1.0)
    cf["_vol_score"] = 1.0 - (cf["payment_volatility"] / vol_q95).clip(0, 1)
    cf["_dispute_score"] = 1.0 - cf["dispute_ratio"].clip(0, 1)
    cf["_ptp_score"] = cf["ptp_kept_ratio"].clip(0, 1)
    cf["_trend_score"] = 1.0 - (cf["payment_trend_30d"].clip(-30, 30) + 30) / 60

    cf["payment_score"] = (
        0.30 * cf["_late_score"]
        + 0.20 * cf["_vol_score"]
        + 0.15 * cf["_dispute_score"]
        + 0.20 * cf["_ptp_score"]
        + 0.15 * cf["_trend_score"]
    ).round(3)

    cf["expected_delay"] = cf["avg_payment_delay"].round(2)

    cf["risk_segment"] = pd.cut(
        cf["payment_score"],
        bins=[-0.01, 0.4, 0.7, 1.01],
        labels=["HIGH", "MEDIUM", "LOW"],
    )

    scores = cf[
        ["customer_id", "payment_score", "expected_delay", "risk_segment"]
    ].copy()
    scores["score_date"] = REFERENCE_DATE.strftime("%Y-%m-%d")
    scores["model_version"] = "cbm-v1.0"

    logger.info("  customer_payment_scores shape: %s", scores.shape)
    logger.info(
        "  risk_segment distribution:\n%s",
        scores["risk_segment"].value_counts().to_string(),
    )
    return scores


# ===================================================================
# 3. INVOICE FEATURES
# ===================================================================
def build_invoice_features(tables):
    """Build invoice_features from invoices + payments + customers."""
    logger.info("--- Building invoice_features ---")

    invoices = tables["invoices"].copy()
    payments = tables["payments"].copy()
    customers = tables["customers"].copy()

    # Payment terms from customer
    customers["payment_terms"] = customers["credit_terms"]

    # Invoice age and days past due
    invoices["invoice_age_days"] = (REFERENCE_DATE - invoices["invoice_date"]).dt.days
    invoices["days_past_due"] = (
        (REFERENCE_DATE - invoices["due_date"]).dt.days.clip(lower=0)
    )

    # Invoice amount bucket and percentile per customer
    invoices["amount_percentile_customer"] = (
        invoices.groupby("customer_id")["invoice_amount"].rank(pct=True).round(3)
    )
    cust_mean = (
        invoices.groupby("customer_id")["invoice_amount"]
        .mean()
        .reset_index(name="cust_mean_amt")
    )
    invoices = invoices.merge(cust_mean, on="customer_id", how="left")
    conditions = [
        invoices["invoice_amount"] <= invoices["cust_mean_amt"] * 0.5,
        invoices["invoice_amount"] <= invoices["cust_mean_amt"] * 1.5,
    ]
    invoices["invoice_amount_bucket"] = np.select(
        conditions, ["SMALL", "MEDIUM"], default="LARGE"
    )

    # Payment terms
    invoices = invoices.merge(
        customers[["customer_id", "payment_terms"]], on="customer_id", how="left"
    )

    # Partial payment info from AR payments
    ar_payments = payments[payments["reference_type"] == "AR"]
    partial_info = (
        ar_payments.groupby("reference_id")["payment_amount"]
        .sum()
        .reset_index(name="partial_payment_amount")
    )
    invoices = invoices.merge(
        partial_info, left_on="invoice_id", right_on="reference_id", how="left"
    )
    invoices["partial_payment_amount"] = invoices["partial_payment_amount"].fillna(0)
    invoices["partial_payment_flag"] = invoices["partial_payment_amount"] > 0

    inv_features = invoices[
        [
            "invoice_id", "customer_id", "invoice_date", "due_date",
            "invoice_amount", "invoice_age_days", "days_past_due",
            "invoice_amount_bucket", "amount_percentile_customer",
            "payment_terms", "dispute_flag", "partial_payment_flag",
            "partial_payment_amount",
        ]
    ].copy()
    inv_features["feature_date"] = REFERENCE_DATE.strftime("%Y-%m-%d")

    logger.info("  invoice_features shape: %s", inv_features.shape)
    return inv_features


# ===================================================================
# 4. COLLECTIONS FEATURES
# ===================================================================
def build_collections_features(tables, customer_features):
    """Build collections_features from collections_events."""
    logger.info("--- Building collections_features ---")

    collections = tables["collections_events"].copy()
    invoices = tables["invoices"].copy()

    # Counts per invoice
    reminder_count = (
        collections[collections["event_type"] == "REMINDER"]
        .groupby("invoice_id")
        .size()
        .reset_index(name="reminder_count")
    )
    call_count = (
        collections[collections["event_type"] == "CALL"]
        .groupby("invoice_id")
        .size()
        .reset_index(name="call_count")
    )

    # PTP info
    ptp_events = collections[collections["event_type"] == "PTP"]
    ptp_flag = (
        ptp_events.groupby("invoice_id")
        .agg(
            promise_to_pay_flag=("event_type", "count"),
            promise_to_pay_date=("promise_to_pay_date", "max"),
        )
        .reset_index()
    )
    ptp_flag["promise_to_pay_flag"] = ptp_flag["promise_to_pay_flag"] > 0

    # Days since last contact
    last_contact = (
        collections.groupby("invoice_id")["event_date"]
        .max()
        .reset_index(name="last_contact_date")
    )
    last_contact["days_since_last_contact"] = (
        REFERENCE_DATE - last_contact["last_contact_date"]
    ).dt.days
    last_contact = last_contact[["invoice_id", "days_since_last_contact"]]

    # Escalation status
    esc_order = {
        "INVOICE_VIEWED": 0, "PARTIAL_PAYMENT": 0,
        "REMINDER": 1, "CALL": 1, "PTP": 1,
        "DISPUTE": 2, "ESCALATION": 3,
    }
    collections["esc_rank"] = collections["event_type"].map(esc_order).fillna(0)
    max_esc = collections.groupby("invoice_id")["esc_rank"].max().reset_index()
    esc_map = {0: "NONE", 1: "REMINDER", 2: "FORMAL", 3: "LEGAL"}
    max_esc["escalation_status"] = max_esc["esc_rank"].map(esc_map).fillna("NONE")
    max_esc = max_esc[["invoice_id", "escalation_status"]]

    # PTP kept ratio at customer level
    cust_ptp = customer_features[["customer_id", "ptp_kept_ratio"]].rename(
        columns={"ptp_kept_ratio": "ptp_kept_ratio_customer"}
    )

    # Merge all on invoice_id
    all_invoices = invoices[["invoice_id", "customer_id"]].copy()
    cf = all_invoices[["invoice_id"]].drop_duplicates()
    for df in [reminder_count, call_count, ptp_flag, last_contact, max_esc]:
        cf = cf.merge(df, on="invoice_id", how="left")

    # Add customer-level ptp ratio
    cf = cf.merge(
        all_invoices[["invoice_id", "customer_id"]], on="invoice_id", how="left"
    )
    cf = cf.merge(cust_ptp, on="customer_id", how="left")
    cf = cf.drop(columns=["customer_id"])

    # Fill defaults
    cf["reminder_count"] = cf["reminder_count"].fillna(0).astype(int)
    cf["call_count"] = cf["call_count"].fillna(0).astype(int)
    cf["promise_to_pay_flag"] = cf["promise_to_pay_flag"].fillna(False)
    cf["days_since_last_contact"] = cf["days_since_last_contact"].fillna(-1).astype(int)
    cf["ptp_kept_ratio_customer"] = cf["ptp_kept_ratio_customer"].fillna(0)
    cf["escalation_status"] = cf["escalation_status"].fillna("NONE")

    logger.info("  collections_features shape: %s", cf.shape)
    return cf


# ===================================================================
# 5. VENDOR FEATURES
# ===================================================================
def build_vendor_features(tables):
    """Build vendor_features from bills, payments, purchase_orders, non_invoice_payments."""
    logger.info("--- Building vendor_features ---")

    bills = tables["bills"].copy()
    payments = tables["payments"].copy()
    vendors = tables["vendors"].copy()
    pos = tables["purchase_orders"].copy()
    non_inv_pay = tables["non_invoice_payments"].copy()

    ap_payments = payments[payments["reference_type"] == "AP"].copy()

    # Join AP payments to bills
    bill_pay = bills.merge(
        ap_payments[["reference_id", "payment_date", "payment_amount"]],
        left_on="bill_id",
        right_on="reference_id",
        how="left",
    )
    bill_pay["payment_cycle_days"] = (
        bill_pay["payment_date"] - bill_pay["bill_date"]
    ).dt.days
    bill_pay["days_late"] = (
        bill_pay["payment_date"] - bill_pay["due_date"]
    ).dt.days

    paid_bills = bill_pay.dropna(subset=["payment_date"])

    # Per-vendor aggregation
    vend_stats = (
        paid_bills.groupby("vendor_id")
        .agg(
            avg_payment_cycle_days=("payment_cycle_days", "mean"),
            payment_volatility=("payment_cycle_days", "std"),
            late_payment_ratio=("days_late", lambda x: (x > 0).mean()),
            avg_invoice_amount=("bill_amount", "mean"),
            invoice_count=("bill_id", "nunique"),
        )
        .reset_index()
    )
    vend_stats["payment_volatility"] = vend_stats["payment_volatility"].fillna(0)

    # Discount capture ratio
    vend_stats2 = (
        paid_bills.groupby("vendor_id")
        .agg(discount_capture_ratio=("days_late", lambda x: (x < 0).mean()))
        .reset_index()
    )

    # Vendor chase frequency (payments per active month)
    paid_bills_copy = paid_bills.copy()
    paid_bills_copy["pay_month"] = paid_bills_copy["payment_date"].dt.to_period("M")
    chase = (
        paid_bills_copy.groupby("vendor_id")["pay_month"]
        .nunique()
        .reset_index(name="active_months")
    )
    chase = chase.merge(
        paid_bills_copy.groupby("vendor_id").size().reset_index(name="total_pays"),
        on="vendor_id",
    )
    chase["vendor_chase_frequency"] = (
        (chase["total_pays"] / chase["active_months"]).round(0).astype(int)
    )
    chase = chase[["vendor_id", "vendor_chase_frequency"]]

    # Last payment date
    last_pay = (
        paid_bills.groupby("vendor_id")["payment_date"]
        .max()
        .reset_index(name="last_payment_date")
    )

    # PO to bill lag
    po_bill = pos.merge(
        bills[["bill_id", "vendor_id", "bill_date"]], on="vendor_id", how="inner"
    )
    po_bill["po_to_bill_days"] = (po_bill["bill_date"] - po_bill["po_date"]).dt.days
    po_lag = (
        po_bill[po_bill["po_to_bill_days"] > 0]
        .groupby("vendor_id")["po_to_bill_days"]
        .mean()
        .reset_index(name="po_to_bill_lag")
    )

    # Advance payment ratio
    vend_nip = non_inv_pay[non_inv_pay["party_type"] == "VENDOR"]
    advance_vend = vend_nip[vend_nip["payment_type"] == "ADVANCE"]
    adv_amt = (
        advance_vend.groupby("party_id")["amount"]
        .sum()
        .reset_index(name="advance_amount")
    )
    adv_amt = adv_amt.rename(columns={"party_id": "vendor_id"})
    total_vend_pay = (
        paid_bills.groupby("vendor_id")["payment_amount"]
        .sum()
        .reset_index(name="total_pay_amount")
    )
    adv_ratio = adv_amt.merge(total_vend_pay, on="vendor_id", how="left")
    adv_ratio["advance_payment_ratio"] = np.where(
        adv_ratio["total_pay_amount"] > 0,
        adv_ratio["advance_amount"] / adv_ratio["total_pay_amount"],
        0,
    )
    adv_ratio = adv_ratio[["vendor_id", "advance_payment_ratio"]]

    # Merge all
    vf = vendors[["vendor_id"]].copy()
    for df in [vend_stats, vend_stats2, chase, last_pay, po_lag, adv_ratio]:
        vf = vf.merge(df, on="vendor_id", how="left")

    fill_zero = [
        "avg_payment_cycle_days", "payment_volatility", "discount_capture_ratio",
        "late_payment_ratio", "vendor_chase_frequency", "avg_invoice_amount",
        "invoice_count", "po_to_bill_lag", "advance_payment_ratio",
    ]
    for col in fill_zero:
        if col in vf.columns:
            vf[col] = vf[col].fillna(0)

    vf["last_payment_date"] = vf["last_payment_date"].fillna(pd.NaT)
    vf["feature_date"] = REFERENCE_DATE.strftime("%Y-%m-%d")
    vf["feature_version"] = "v1.0.0"

    logger.info("  vendor_features shape: %s", vf.shape)
    return vf


# ===================================================================
# 6. BILL FEATURES
# ===================================================================
def build_bill_features(tables):
    """Build bill_features from bills."""
    logger.info("--- Building bill_features ---")

    bills = tables["bills"].copy()

    bills["bill_age_days"] = (REFERENCE_DATE - bills["bill_date"]).dt.days
    bills["days_past_due"] = (
        (REFERENCE_DATE - bills["due_date"]).dt.days.clip(lower=0)
    )

    # Amount bucket per vendor
    vend_mean = (
        bills.groupby("vendor_id")["bill_amount"]
        .mean()
        .reset_index(name="vend_mean_amt")
    )
    bills = bills.merge(vend_mean, on="vendor_id", how="left")

    bills["amount_percentile_vendor"] = (
        bills.groupby("vendor_id")["bill_amount"].rank(pct=True).round(3)
    )

    conditions = [
        bills["bill_amount"] <= bills["vend_mean_amt"] * 0.5,
        bills["bill_amount"] <= bills["vend_mean_amt"] * 1.5,
    ]
    bills["bill_amount_bucket"] = np.select(
        conditions, ["SMALL", "MEDIUM"], default="LARGE"
    )

    # Approval status
    bills["approval_status"] = np.where(
        bills["bill_status"].isin(["PAID", "DEFERRED"]), "APPROVED", "PENDING"
    )

    # Early payment eligible (within 10 days of due date, not past due)
    bills["early_payment_eligible"] = (
        ((bills["due_date"] - REFERENCE_DATE).dt.days > 0)
        & ((bills["due_date"] - REFERENCE_DATE).dt.days <= 10)
    )

    # Penalty accruing
    bills["penalty_accruing"] = (bills["days_past_due"] > 0) & (
        bills["bill_status"].isin(["OPEN", "APPROVED"])
    )

    bf = bills[
        [
            "bill_id", "vendor_id", "bill_age_days", "days_past_due",
            "bill_amount", "bill_amount_bucket", "amount_percentile_vendor",
            "approval_status", "early_payment_eligible", "penalty_accruing",
        ]
    ].copy()
    bf["feature_date"] = REFERENCE_DATE.strftime("%Y-%m-%d")

    logger.info("  bill_features shape: %s", bf.shape)
    return bf


# ===================================================================
# MAIN
# ===================================================================
def run():
    """Build all feature tables and save to Data/features/."""
    logger.info("=" * 60)
    logger.info("STEP: Feature Table Generation - START")
    logger.info("=" * 60)

    os.makedirs(FEATURE_DIR, exist_ok=True)
    tables = _load_raw_tables()

    customer_features = build_customer_features(tables)
    customer_payment_scores = build_customer_payment_scores(customer_features)
    invoice_features = build_invoice_features(tables)
    collections_features = build_collections_features(tables, customer_features)
    vendor_features = build_vendor_features(tables)
    bill_features = build_bill_features(tables)

    outputs = {
        "customer_features": customer_features,
        "customer_payment_scores": customer_payment_scores,
        "invoice_features": invoice_features,
        "collections_features": collections_features,
        "vendor_features": vendor_features,
        "bill_features": bill_features,
    }
    for name, df in outputs.items():
        path = FEATURE_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("Saved %-30s -> %s  (%d rows)", name, path, len(df))

    logger.info("=" * 60)
    logger.info("STEP: Feature Table Generation - COMPLETE")
    logger.info("=" * 60)

    return outputs


if __name__ == "__main__":
    run()
