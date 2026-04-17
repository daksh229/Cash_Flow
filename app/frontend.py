"""
Cash Flow Forecasting - Streamlit Frontend (Dual Mode)
========================================================
Two modes per model:
  - Existing Record: Select ID from dropdown, features auto-fetched
  - New Entry: Fill raw business fields, backend derives features
"""

import streamlit as st
import requests
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Cash Flow Forecasting",
    page_icon="$",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def api_call(endpoint, method="GET", data=None):
    try:
        if method == "GET":
            resp = requests.get(f"{API_URL}{endpoint}", timeout=10)
        else:
            resp = requests.post(f"{API_URL}{endpoint}", json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        st.error("Cannot connect to API. Start the backend: `python app/api.py`")
        return None
    except requests.HTTPError as e:
        st.error(f"API Error: {e.response.text}")
        return None


@st.cache_data(ttl=60)
def fetch_ids(endpoint):
    result = api_call(endpoint)
    if result:
        key = [k for k in result.keys() if k.endswith("_ids")][0]
        return result[key]
    return []


def display_result(result):
    """Common result display for all models."""
    if not result:
        return

    st.markdown("---")

    # Mode badge
    mode = result.get("mode", "unknown")
    mode_label = "Existing Record" if mode == "lookup" else "New Entry"
    st.caption(f"Mode: **{mode_label}**")

    return result


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Cash Flow Forecasting")
st.sidebar.markdown("---")

health = api_call("/health")
if health:
    st.sidebar.success(f"API: {health['status']}")
    st.sidebar.write("**Models:**")
    for m in health.get("models_loaded", []):
        st.sidebar.write(f"  - {m}")
else:
    st.sidebar.error("API not available")

st.sidebar.markdown("---")

st.sidebar.subheader("Models")
model_choice = st.sidebar.radio(
    "Select Model",
    [
        "S1 - AR Collections",
        "S2 - AP Payment",
        "Credit Risk",
        "S3 - WIP Billing Forecast",
        "S4 - Pipeline Forecast",
        "S5 - Contingent Inflows",
        "S6 - Expense Forecast",
        "S7 - Cash Position",
        "Recommendations",
    ],
    index=0,
)

st.sidebar.markdown("---")
show_metrics = st.sidebar.checkbox("Show Evaluation Metrics", value=False)


# ===================================================================
# S1 - AR COLLECTIONS PREDICTION
# ===================================================================
if model_choice == "S1 - AR Collections":
    st.title("S1 - AR Collections Prediction")
    st.markdown("Predict **days_to_pay** for an AR invoice.")

    mode = st.radio(
        "Input Mode",
        ["Existing Invoice (Lookup)", "New Invoice"],
        horizontal=True,
    )

    if mode == "Existing Invoice (Lookup)":
        invoice_ids = fetch_ids("/lookup/invoices?limit=500")
        if not invoice_ids:
            st.warning("No invoices found. Run the feature table pipeline first.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                selected = st.selectbox("Select Invoice ID", invoice_ids, index=0)
            with col2:
                st.write("")
                st.write("")
                btn = st.button("Predict", type="primary", use_container_width=True)

            if btn and selected:
                with st.spinner("Fetching features and predicting..."):
                    result = api_call(f"/predict/s1/{selected}")
                if result:
                    display_result(result)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Predicted Days to Pay", f"{result['prediction']} days")
                    c2.metric("Baseline", f"{result.get('baseline_prediction', 'N/A')} days")
                    c3.metric("Confidence", result.get("confidence", "N/A"))
                    c4.metric("Divergence", f"{result['details'].get('model_divergence', 'N/A')} days")

                    st.subheader("Input Summary (auto-fetched)")
                    summary = result.get("input_summary", {})
                    s1, s2, s3, s4 = st.columns(4)
                    s1.write(f"**Invoice:** {summary.get('invoice_id', 'N/A')}")
                    s2.write(f"**Customer:** {summary.get('customer_id', 'N/A')}")
                    s3.write(f"**Amount:** ${summary.get('invoice_amount', 0):,.2f}")
                    s4.write(f"**Risk:** {summary.get('risk_segment', 'N/A')}")

                    with st.expander("Full Details"):
                        st.json(result.get("details", {}))

    else:  # New Invoice
        st.markdown("Enter raw invoice details. Customer features are auto-fetched if customer exists, otherwise global defaults are used.")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Invoice Details")
            invoice_amount = st.number_input("Invoice Amount ($)", value=50000.0, step=1000.0, min_value=0.0)
            invoice_date = st.date_input("Invoice Date", value=pd.Timestamp("2026-03-15"))
            due_date = st.date_input("Due Date", value=pd.Timestamp("2026-04-15"))
            payment_terms = st.selectbox("Payment Terms", ["NET15", "NET30", "NET45", "NET60", "NET90"], index=1)

        with col2:
            st.subheader("Additional Info")
            dispute_flag = st.selectbox("Dispute?", [("No", False), ("Yes", True)], format_func=lambda x: x[0])[1]
            partial_payment_amount = st.number_input("Partial Payment Amount ($)", value=0.0, step=100.0, min_value=0.0)
            customer_id = st.text_input(
                "Customer ID (optional)",
                placeholder="e.g. CUST-93810 (leave empty for new customer)",
            )

        if customer_id:
            st.info(f"Will fetch features for **{customer_id}** from Feature Store")
        else:
            st.warning("No customer ID provided. Global average defaults will be used for customer behaviour features.")

        st.markdown("---")
        if st.button("Predict Days to Pay", type="primary", use_container_width=True):
            payload = {
                "invoice_amount": invoice_amount,
                "invoice_date": str(invoice_date),
                "due_date": str(due_date),
                "payment_terms": payment_terms,
                "dispute_flag": dispute_flag,
                "partial_payment_amount": partial_payment_amount,
                "customer_id": customer_id if customer_id.strip() else None,
            }

            with st.spinner("Computing features and predicting..."):
                result = api_call("/predict/s1/new", method="POST", data=payload)

            if result:
                display_result(result)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Predicted Days to Pay", f"{result['prediction']} days")
                c2.metric("Baseline", f"{result.get('baseline_prediction', 'N/A')} days")
                c3.metric("Confidence", result.get("confidence", "N/A"))
                c4.metric("Divergence", f"{result['details'].get('model_divergence', 'N/A')} days")

                st.subheader("Derived Input Summary")
                summary = result.get("input_summary", {})
                s1, s2 = st.columns(2)
                s1.write(f"**Customer Source:** {summary.get('customer_source', 'N/A')}")
                s1.write(f"**Invoice Age:** {summary.get('invoice_age_days', 0)} days")
                s1.write(f"**Days Past Due:** {summary.get('days_past_due', 0)}")
                s2.write(f"**Payment Score:** {summary.get('payment_score', 'N/A')}")
                s2.write(f"**Risk Segment:** {summary.get('risk_segment', 'N/A')}")

                with st.expander("Full Details"):
                    st.json(result.get("details", {}))

    if show_metrics:
        st.markdown("---")
        st.subheader("S1 Model Evaluation Metrics")
        metrics = api_call("/metrics/s1_ar_prediction")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# S2 - AP PAYMENT PREDICTION
# ===================================================================
elif model_choice == "S2 - AP Payment":
    st.title("S2 - AP Payment Prediction")
    st.markdown("Predict **adjustment_delta** (days early/late vs scheduled) for vendor bills.")

    mode = st.radio(
        "Input Mode",
        ["Existing Bill (Lookup)", "New Bill"],
        horizontal=True,
    )

    if mode == "Existing Bill (Lookup)":
        bill_ids = fetch_ids("/lookup/bills?limit=500")
        if not bill_ids:
            st.warning("No bills found. Run the feature table pipeline first.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                selected = st.selectbox("Select Bill ID", bill_ids, index=0)
            with col2:
                st.write("")
                st.write("")
                btn = st.button("Predict", type="primary", use_container_width=True)

            if btn and selected:
                with st.spinner("Fetching features and predicting..."):
                    result = api_call(f"/predict/s2/{selected}")
                if result:
                    display_result(result)
                    delta = result["prediction"]
                    direction = "LATER" if delta > 0 else "EARLIER"

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Adjustment Delta", f"{delta:+.1f} days")
                    c2.metric("Direction", f"{direction} than scheduled")
                    c3.metric("Confidence", result.get("confidence", "N/A"))
                    c4.metric("Baseline", f"{result.get('baseline_prediction', 'N/A')} days")

                    st.subheader("Input Summary (auto-fetched)")
                    summary = result.get("input_summary", {})
                    s1, s2, s3, s4 = st.columns(4)
                    s1.write(f"**Bill:** {summary.get('bill_id', 'N/A')}")
                    s2.write(f"**Vendor:** {summary.get('vendor_id', 'N/A')}")
                    s3.write(f"**Amount:** ${summary.get('bill_amount', 0):,.2f}")
                    s4.write(f"**Status:** {summary.get('approval_status', 'N/A')}")

                    with st.expander("Full Details"):
                        st.json(result.get("details", {}))

    else:  # New Bill
        st.markdown("Enter raw bill details. Vendor features are auto-fetched if vendor exists.")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Bill Details")
            bill_amount = st.number_input("Bill Amount ($)", value=35000.0, step=1000.0, min_value=0.0)
            bill_date = st.date_input("Bill Date", value=pd.Timestamp("2026-03-20"))
            due_date = st.date_input("Due Date", value=pd.Timestamp("2026-04-20"))

        with col2:
            st.subheader("Additional Info")
            approval_status = st.selectbox("Approval Status", ["APPROVED", "PENDING"])
            vendor_id = st.text_input(
                "Vendor ID (optional)",
                placeholder="e.g. VEN-51043 (leave empty for new vendor)",
            )

        if vendor_id:
            st.info(f"Will fetch features for **{vendor_id}** from Feature Store")
        else:
            st.warning("No vendor ID provided. Global average defaults will be used.")

        st.markdown("---")
        if st.button("Predict Payment Adjustment", type="primary", use_container_width=True):
            payload = {
                "bill_amount": bill_amount,
                "bill_date": str(bill_date),
                "due_date": str(due_date),
                "approval_status": approval_status,
                "vendor_id": vendor_id if vendor_id.strip() else None,
            }

            with st.spinner("Computing features and predicting..."):
                result = api_call("/predict/s2/new", method="POST", data=payload)

            if result:
                display_result(result)
                delta = result["prediction"]
                direction = "LATER" if delta > 0 else "EARLIER"

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Adjustment Delta", f"{delta:+.1f} days")
                c2.metric("Direction", f"{direction} than scheduled")
                c3.metric("Confidence", result.get("confidence", "N/A"))
                c4.metric("Baseline", f"{result.get('baseline_prediction', 'N/A')} days")

                st.subheader("Derived Input Summary")
                summary = result.get("input_summary", {})
                s1, s2 = st.columns(2)
                s1.write(f"**Vendor Source:** {summary.get('vendor_source', 'N/A')}")
                s1.write(f"**Bill Age:** {summary.get('bill_age_days', 0)} days")
                s2.write(f"**Days Past Due:** {summary.get('days_past_due', 0)}")

                with st.expander("Full Details"):
                    st.json(result.get("details", {}))

    if show_metrics:
        st.markdown("---")
        st.subheader("S2 Model Evaluation Metrics")
        metrics = api_call("/metrics/s2_ap_prediction")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# CREDIT RISK ASSESSMENT
# ===================================================================
elif model_choice == "Credit Risk":
    st.title("Credit Risk Assessment")
    st.markdown("Classify customer risk segment: **LOW / MEDIUM / HIGH**")

    mode = st.radio(
        "Input Mode",
        ["Existing Customer (Lookup)", "New Customer"],
        horizontal=True,
    )

    if mode == "Existing Customer (Lookup)":
        customer_ids = fetch_ids("/lookup/customers?limit=500")
        if not customer_ids:
            st.warning("No customers found. Run the feature table pipeline first.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                selected = st.selectbox("Select Customer ID", customer_ids, index=0)
            with col2:
                st.write("")
                st.write("")
                btn = st.button("Assess Risk", type="primary", use_container_width=True)

            if btn and selected:
                with st.spinner("Fetching features and classifying..."):
                    result = api_call(f"/predict/credit_risk/{selected}")
                if result:
                    display_result(result)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Risk Segment", result["prediction"])
                    c2.metric("Confidence", result.get("confidence", "N/A"))
                    c3.metric("Baseline", result.get("baseline_prediction", "N/A"))

                    if result.get("probabilities"):
                        st.subheader("Class Probabilities")
                        prob_df = pd.DataFrame(
                            list(result["probabilities"].items()),
                            columns=["Risk Level", "Probability"],
                        )
                        st.bar_chart(prob_df.set_index("Risk Level"))

                    st.subheader("Customer Profile (auto-fetched)")
                    summary = result.get("input_summary", {})
                    s1, s2, s3 = st.columns(3)
                    s1.write(f"**Customer:** {summary.get('customer_id', 'N/A')}")
                    s1.write(f"**Avg Delay:** {summary.get('avg_payment_delay', 0):.1f} days")
                    s2.write(f"**Late Ratio:** {summary.get('late_payment_ratio', 0):.2f}")
                    s2.write(f"**Volatility:** {summary.get('payment_volatility', 0):.1f}")
                    s3.write(f"**DSO:** {summary.get('days_sales_outstanding', 0):.1f}")
                    s3.write(f"**Invoices:** {summary.get('invoice_count', 0)}")

                    with st.expander("Full Details"):
                        st.json(result.get("details", {}))

    else:  # New Customer
        st.markdown("Enter payment behaviour metrics for a new customer. "
                     "These would typically come from initial credit assessment or external data.")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Payment Behaviour")
            avg_payment_delay = st.number_input("Avg Payment Delay (days)", value=5.0, step=1.0, help="Average days late across invoices. 0 = pays on time.")
            late_payment_ratio = st.slider("Late Payment Ratio", 0.0, 1.0, 0.2, help="Fraction of invoices paid late (0.0-1.0)")
            payment_volatility = st.number_input("Payment Volatility", value=8.0, step=1.0, help="Std dev of payment timing. High = unpredictable.")
            dispute_ratio = st.slider("Dispute Ratio", 0.0, 1.0, 0.05, help="Fraction of invoices with disputes")

        with col2:
            st.subheader("Financial Profile")
            days_sales_outstanding = st.number_input("DSO (Days Sales Outstanding)", value=35.0, step=5.0, help="Outstanding AR / (revenue / 365)")
            invoice_count = st.number_input("Historical Invoice Count", value=0, min_value=0, step=1, help="0 = brand new customer")
            ptp_kept_ratio = st.slider("PTP Kept Ratio", 0.0, 1.0, 1.0, help="Fraction of promises-to-pay honoured. 1.0 = always keeps promises.")

        st.markdown("---")
        if st.button("Assess Credit Risk", type="primary", use_container_width=True):
            payload = {
                "avg_payment_delay": avg_payment_delay,
                "late_payment_ratio": late_payment_ratio,
                "payment_volatility": payment_volatility,
                "dispute_ratio": dispute_ratio,
                "days_sales_outstanding": days_sales_outstanding,
                "invoice_count": invoice_count,
                "ptp_kept_ratio": ptp_kept_ratio,
            }

            with st.spinner("Computing features and classifying..."):
                result = api_call("/predict/credit_risk/new", method="POST", data=payload)

            if result:
                display_result(result)
                c1, c2, c3 = st.columns(3)
                c1.metric("Risk Segment", result["prediction"])
                c2.metric("Confidence", result.get("confidence", "N/A"))
                c3.metric("Baseline", result.get("baseline_prediction", "N/A"))

                if result.get("probabilities"):
                    st.subheader("Class Probabilities")
                    prob_df = pd.DataFrame(
                        list(result["probabilities"].items()),
                        columns=["Risk Level", "Probability"],
                    )
                    st.bar_chart(prob_df.set_index("Risk Level"))

                st.subheader("Input Summary")
                summary = result.get("input_summary", {})
                st.write(f"**Customer:** {summary.get('customer_id', 'N/A')}")
                s1, s2, s3 = st.columns(3)
                s1.write(f"**Avg Delay:** {summary.get('avg_payment_delay', 0):.1f} days")
                s2.write(f"**Late Ratio:** {summary.get('late_payment_ratio', 0):.2f}")
                s3.write(f"**DSO:** {summary.get('days_sales_outstanding', 0):.1f}")

                with st.expander("Full Details"):
                    st.json(result.get("details", {}))

    if show_metrics:
        st.markdown("---")
        st.subheader("Credit Risk Model Evaluation Metrics")
        metrics = api_call("/metrics/credit_risk")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# S3 - WIP BILLING FORECAST
# ===================================================================
elif model_choice == "S3 - WIP Billing Forecast":
    st.title("S3 - WIP Billing Forecast")
    st.markdown("Rule-based forecast of expected cash from **project milestones**. "
                "Select a project to see milestone-level billing forecast.")

    view_mode = st.radio(
        "View",
        ["Lookup by Project", "Full Summary"],
        horizontal=True,
    )

    if view_mode == "Lookup by Project":
        project_ids = fetch_ids("/lookup/projects?limit=500")
        if not project_ids:
            st.warning("No S3 forecast data. Run `python pipeline/run_s3_wip_forecast.py` first.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                selected = st.selectbox("Select Project ID", project_ids, index=0)
            with col2:
                st.write("")
                st.write("")
                btn = st.button("View Forecast", type="primary", use_container_width=True)

            if btn and selected:
                with st.spinner("Loading forecast..."):
                    result = api_call(f"/forecast/s3/{selected}")

                if result:
                    summary = result.get("summary", {})
                    st.markdown("---")

                    # Summary cards
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Project", summary.get("project_id", "N/A"))
                    c2.metric("Customer", summary.get("customer_id", "N/A"))
                    c3.metric("Type", summary.get("project_type", "N/A"))
                    c4.metric("Total Forecast", f"${summary.get('total_forecast', 0):,.2f}")

                    st.write(f"**Milestones:** {summary.get('milestones', 0)} | "
                             f"**Date Range:** {summary.get('date_range', 'N/A')}")

                    # Milestone table
                    st.subheader("Milestone Forecast Details")
                    records = result.get("records", [])
                    if records:
                        display_cols = [
                            "milestone_name", "completion_pct", "completion_status",
                            "billing_amount", "expected_completion_date",
                            "expected_invoice_date", "expected_cash_date",
                            "confidence_tier",
                        ]
                        df = pd.DataFrame(records)
                        available = [c for c in display_cols if c in df.columns]
                        st.dataframe(df[available], use_container_width=True)

                        # Timeline chart
                        st.subheader("Cash Timeline")
                        df["expected_cash_date"] = pd.to_datetime(df["expected_cash_date"])
                        chart_data = df.set_index("expected_cash_date")[["forecast_amount"]]
                        st.bar_chart(chart_data)

    else:  # Full Summary
        with st.spinner("Loading S3 summary..."):
            summary = api_call("/forecast/s3/summary/all")

        if summary:
            st.markdown("---")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Milestones", summary.get("total_milestones", 0))
            c2.metric("Projects", summary.get("total_projects", 0))
            c3.metric("Customers", summary.get("total_customers", 0))
            c4.metric("Total Forecast", f"${summary.get('total_forecast', 0):,.2f}")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("By Confidence Tier")
                conf = summary.get("by_confidence", {})
                if conf:
                    conf_df = pd.DataFrame(
                        [(k, v) for k, v in conf.items()],
                        columns=["Confidence", "Amount"],
                    )
                    st.bar_chart(conf_df.set_index("Confidence"))

            with col2:
                st.subheader("By Project Type")
                ptype = summary.get("by_project_type", {})
                if ptype:
                    ptype_df = pd.DataFrame(
                        [(k, v) for k, v in ptype.items()],
                        columns=["Project Type", "Amount"],
                    )
                    st.bar_chart(ptype_df.set_index("Project Type"))

    if show_metrics:
        st.markdown("---")
        st.subheader("S3 Forecast Report")
        metrics = api_call("/forecast/s3/summary/report")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# S4 - SALES PIPELINE FORECAST
# ===================================================================
elif model_choice == "S4 - Pipeline Forecast":
    st.title("S4 - Sales Pipeline Forecast")
    st.markdown("Rule-based forecast of expected cash from **open CRM deals**, "
                "weighted by stage probability.")

    view_mode = st.radio(
        "View",
        ["Lookup by Deal", "Full Summary"],
        horizontal=True,
    )

    if view_mode == "Lookup by Deal":
        deal_ids = fetch_ids("/lookup/deals?limit=500")
        if not deal_ids:
            st.warning("No S4 forecast data. Run `python pipeline/run_s4_pipeline_forecast.py` first.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                selected = st.selectbox("Select Deal / Opportunity ID", deal_ids, index=0)
            with col2:
                st.write("")
                st.write("")
                btn = st.button("View Forecast", type="primary", use_container_width=True)

            if btn and selected:
                with st.spinner("Loading forecast..."):
                    result = api_call(f"/forecast/s4/{selected}")

                if result:
                    summary = result.get("summary", {})
                    st.markdown("---")

                    # Summary cards
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Deal", summary.get("opportunity_id", "N/A"))
                    c2.metric("Stage", summary.get("crm_stage", "N/A"))
                    c3.metric("Deal Value", f"${summary.get('deal_value', 0):,.2f}")
                    c4.metric("Weighted Forecast", f"${summary.get('total_weighted_forecast', 0):,.2f}")

                    s1, s2, s3 = st.columns(3)
                    s1.write(f"**Customer:** {summary.get('customer_id', 'N/A')}")
                    s2.write(f"**Stage Probability:** {summary.get('stage_probability', 0):.0%}")
                    s3.write(f"**Milestones:** {summary.get('milestones', 0)}")

                    # Milestone table
                    st.subheader("Milestone Forecast Details")
                    records = result.get("records", [])
                    if records:
                        display_cols = [
                            "milestone_sequence", "milestone_weight",
                            "forecast_amount", "expected_close_date",
                            "expected_invoice_date", "expected_cash_date",
                            "confidence_tier",
                        ]
                        df = pd.DataFrame(records)
                        available = [c for c in display_cols if c in df.columns]
                        st.dataframe(df[available], use_container_width=True)

    else:  # Full Summary
        with st.spinner("Loading S4 summary..."):
            summary = api_call("/forecast/s4/summary/all")

        if summary:
            st.markdown("---")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Records", summary.get("total_records", 0))
            c2.metric("Deals", summary.get("total_deals", 0))
            c3.metric("Customers", summary.get("total_customers", 0))
            c4.metric("Total Forecast", f"${summary.get('total_forecast', 0):,.2f}")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("By CRM Stage")
                by_stage = summary.get("by_stage", {})
                if by_stage:
                    stage_df = pd.DataFrame(
                        [(k, v) for k, v in by_stage.items()],
                        columns=["Stage", "Amount"],
                    )
                    st.bar_chart(stage_df.set_index("Stage"))

            with col2:
                st.subheader("By Deal Type")
                by_type = summary.get("by_deal_type", {})
                if by_type:
                    type_df = pd.DataFrame(
                        [(k, v) for k, v in by_type.items()],
                        columns=["Deal Type", "Amount"],
                    )
                    st.bar_chart(type_df.set_index("Deal Type"))

    if show_metrics:
        st.markdown("---")
        st.subheader("S4 Forecast Report")
        metrics = api_call("/forecast/s4/summary/report")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# S5 - CONTINGENT INFLOWS
# ===================================================================
elif model_choice == "S5 - Contingent Inflows":
    st.title("S5 - Contingent Inflows Forecast")
    st.markdown("Scheduled expected inflows from **loans, tax refunds, grants, insurance**, and other non-sales sources.")

    view_mode = st.radio("View", ["Summary", "All Records"], horizontal=True)

    if view_mode == "Summary":
        with st.spinner("Loading S5 summary..."):
            summary = api_call("/forecast/s5/summary/all")

        if summary:
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("Total Records", summary.get("total_records", 0))
            c2.metric("Total Forecast", f"${summary.get('total_forecast', 0):,.2f}")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("By Category")
                by_cat = summary.get("by_category", {})
                if by_cat:
                    cat_df = pd.DataFrame(
                        [(k, v) for k, v in by_cat.items()],
                        columns=["Category", "Amount"],
                    )
                    st.bar_chart(cat_df.set_index("Category"))

            with col2:
                st.subheader("By Confidence")
                by_conf = summary.get("by_confidence", {})
                if by_conf:
                    conf_df = pd.DataFrame(
                        [(k, v) for k, v in by_conf.items()],
                        columns=["Confidence", "Amount"],
                    )
                    st.bar_chart(conf_df.set_index("Confidence"))

            # Approval status breakdown
            st.subheader("By Approval Status")
            by_approval = summary.get("by_approval", {})
            if by_approval:
                appr_df = pd.DataFrame(
                    [(k, v) for k, v in by_approval.items()],
                    columns=["Status", "Amount"],
                )
                st.dataframe(appr_df, use_container_width=True)

    else:  # All Records
        with st.spinner("Loading S5 records..."):
            records = api_call("/forecast/s5/records")

        if records:
            st.markdown("---")
            df = pd.DataFrame(records)
            display_cols = [
                "inflow_id", "category", "amount", "expected_receipt_date",
                "expected_cash_date", "approval_status", "confidence_tier", "notes",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available], use_container_width=True)

            st.subheader("Cash Timeline")
            df["expected_cash_date"] = pd.to_datetime(df["expected_cash_date"])
            timeline = df.groupby("expected_cash_date")["forecast_amount"].sum().reset_index()
            timeline = timeline.set_index("expected_cash_date")
            st.bar_chart(timeline)

    if show_metrics:
        st.markdown("---")
        st.subheader("S5 Forecast Report")
        metrics = api_call("/forecast/s5/summary/report")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# S6 - EXPENSE FORECAST
# ===================================================================
elif model_choice == "S6 - Expense Forecast":
    st.title("S6 - Expense Forecast")
    st.markdown("All planned cash **outflows**: salaries, taxes, renewals, PO-based, seasonal, one-time.")

    view_mode = st.radio("View", ["Summary", "All Records"], horizontal=True)

    if view_mode == "Summary":
        with st.spinner("Loading S6 summary..."):
            summary = api_call("/forecast/s6/summary/all")

        if summary:
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("Total Records", summary.get("total_records", 0))
            c2.metric("Total Outflow", f"${summary.get('total_outflow', 0):,.2f}")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("By Category")
                by_cat = summary.get("by_category", {})
                if by_cat:
                    cat_df = pd.DataFrame(
                        [(k, v) for k, v in by_cat.items()],
                        columns=["Category", "Amount"],
                    )
                    st.bar_chart(cat_df.set_index("Category"))

            with col2:
                st.subheader("By Recurrence Type")
                by_rec = summary.get("by_recurrence", {})
                if by_rec:
                    rec_df = pd.DataFrame(
                        [(k, v) for k, v in by_rec.items()],
                        columns=["Recurrence", "Amount"],
                    )
                    st.bar_chart(rec_df.set_index("Recurrence"))

            st.subheader("By Confidence")
            by_conf = summary.get("by_confidence", {})
            if by_conf:
                conf_df = pd.DataFrame(
                    [(k, v) for k, v in by_conf.items()],
                    columns=["Confidence", "Amount"],
                )
                st.dataframe(conf_df, use_container_width=True)

    else:  # All Records
        with st.spinner("Loading S6 records..."):
            records = api_call("/forecast/s6/records")

        if records:
            st.markdown("---")
            df = pd.DataFrame(records)
            display_cols = [
                "expense_id", "category", "recurrence_type", "amount",
                "obligation_date", "expected_cash_date", "payment_lag_days",
                "confidence_tier", "approved_by", "notes",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available], use_container_width=True)

            st.subheader("Outflow Timeline")
            df["expected_cash_date"] = pd.to_datetime(df["expected_cash_date"])
            timeline = df.groupby("expected_cash_date")["forecast_amount"].sum().abs().reset_index()
            timeline = timeline.set_index("expected_cash_date")
            st.bar_chart(timeline)

    if show_metrics:
        st.markdown("---")
        st.subheader("S6 Forecast Report")
        metrics = api_call("/forecast/s6/summary/report")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# S7 - CASH POSITION (AGGREGATED)
# ===================================================================
elif model_choice == "S7 - Cash Position":
    st.title("S7 - Aggregated Cash Position")
    st.markdown("Unified cash forecast combining **all modules (S1-S6)** with deduplication, "
                "daily/weekly/monthly views, and cumulative balance projection.")

    view_mode = st.radio(
        "View",
        ["Dashboard", "Daily", "Weekly", "Monthly"],
        horizontal=True,
    )

    if view_mode == "Dashboard":
        with st.spinner("Loading S7 summary..."):
            summary = api_call("/forecast/s7/summary")
            monthly = api_call("/forecast/s7/monthly")
            daily = api_call("/forecast/s7/daily")

        if summary:
            st.markdown("---")

            # Top-level KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Inflows", f"${summary.get('total_inflows', 0):,.0f}")
            c2.metric("Total Outflows", f"${summary.get('total_outflows', 0):,.0f}")
            c3.metric("Net Change", f"${summary.get('net_change', 0):,.0f}")
            c4.metric("Closing Balance", f"${summary.get('closing_balance', 0):,.0f}")

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Active Events", summary.get("active_events", 0))
            c6.metric("Suppressed (dedup)", summary.get("suppressed_events", 0))
            c7.metric("Forecast Days", summary.get("total_days", 0))
            c8.metric("Min Cash Position", f"${summary.get('min_position', 0):,.0f}")

            # Cash position chart
            if daily:
                st.subheader("Daily Cumulative Cash Position")
                daily_df = pd.DataFrame(daily)
                daily_df["date"] = pd.to_datetime(daily_df["date"])
                st.line_chart(daily_df.set_index("date")[["cumulative_position"]])

                st.subheader("Daily Inflows vs Outflows")
                st.area_chart(daily_df.set_index("date")[["gross_inflow", "gross_outflow"]])

            # Monthly summary table
            if monthly:
                st.subheader("Monthly Cash Flow Summary")
                monthly_df = pd.DataFrame(monthly)
                st.dataframe(monthly_df, use_container_width=True)

            # By source breakdown
            by_source = summary.get("by_source", {})
            if by_source:
                st.subheader("Contribution by Source Module")
                src_rows = []
                for src, vals in by_source.items():
                    src_rows.append({
                        "Module": src,
                        "Events": vals.get("events", 0),
                        "Total Amount": vals.get("total", 0),
                        "Direction": "Inflow" if vals.get("total", 0) > 0 else "Outflow",
                    })
                src_df = pd.DataFrame(src_rows)
                st.dataframe(src_df, use_container_width=True)

                # Chart
                src_df["Abs Amount"] = src_df["Total Amount"].abs()
                st.bar_chart(src_df.set_index("Module")[["Abs Amount"]])

    elif view_mode == "Daily":
        with st.spinner("Loading daily data..."):
            daily = api_call("/forecast/s7/daily")
        if daily:
            df = pd.DataFrame(daily)
            df["date"] = pd.to_datetime(df["date"])
            st.subheader("Daily Cash Position")
            st.line_chart(df.set_index("date")[["cumulative_position"]])
            st.subheader("Daily Detail")
            st.dataframe(df, use_container_width=True)

    elif view_mode == "Weekly":
        with st.spinner("Loading weekly data..."):
            weekly = api_call("/forecast/s7/weekly")
        if weekly:
            df = pd.DataFrame(weekly)
            st.subheader("Weekly Cash Position")
            st.bar_chart(df.set_index("week")[["gross_inflow", "gross_outflow"]])
            st.subheader("Weekly Detail")
            st.dataframe(df, use_container_width=True)

    elif view_mode == "Monthly":
        with st.spinner("Loading monthly data..."):
            monthly = api_call("/forecast/s7/monthly")
        if monthly:
            df = pd.DataFrame(monthly)
            st.subheader("Monthly Cash Position")
            st.bar_chart(df.set_index("month")[["gross_inflow", "gross_outflow"]])

            st.subheader("Monthly Net & Closing Balance")
            st.line_chart(df.set_index("month")[["closing_position"]])

            st.subheader("Monthly Detail")
            st.dataframe(df, use_container_width=True)

    if show_metrics:
        st.markdown("---")
        st.subheader("S7 Cash Forecast Report")
        metrics = api_call("/forecast/s7/summary/report")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)


# ===================================================================
# RECOMMENDATION ENGINE
# ===================================================================
elif model_choice == "Recommendations":
    st.title("Recommendation Engine")
    st.markdown("Ranked, actionable recommendations for **treasury and finance** decision-makers. "
                "Collections acceleration, vendor deferrals, and expense optimization.")

    view_mode = st.radio("View", ["Inbox", "Summary"], horizontal=True)

    if view_mode == "Inbox":
        with st.spinner("Loading recommendations..."):
            recs = api_call("/recommendations")

        if recs:
            st.markdown("---")
            st.subheader(f"Top {len(recs)} Recommendations")

            for rec in recs:
                rank = rec.get("rank", "?")
                lever = rec.get("lever", "")
                priority = rec.get("priority", "")
                score = rec.get("score", 0)
                cash = rec.get("cash_impact", 0)

                # Priority color
                pri_emoji = {"HIGH": "!!!", "MEDIUM": "!!", "LOW": "!"}.get(priority, "")

                with st.expander(
                    f"#{rank} [{lever}] {rec.get('entity_id', '')} — "
                    f"${cash:,.0f} | {priority} {pri_emoji} | Score: {score:.3f}"
                ):
                    st.write(f"**Action:** {rec.get('action', '')}")
                    st.write(f"**Description:** {rec.get('description', '')}")

                    c1, c2, c3, c4 = st.columns(4)
                    c1.write(f"**Entity:** {rec.get('entity_id', 'N/A')}")
                    c2.write(f"**Customer:** {rec.get('customer_id', 'N/A')}")
                    c3.write(f"**Channel:** {rec.get('channel', 'N/A')}")
                    c4.write(f"**Risk:** {rec.get('risk_segment', 'N/A')}")

                    c5, c6, c7, c8 = st.columns(4)
                    c5.metric("Cash Impact", f"${cash:,.0f}")
                    c6.metric("Score", f"{score:.3f}")
                    c7.metric("Priority", priority)
                    c8.metric("Confidence", rec.get("confidence", "N/A"))
        else:
            st.info("No recommendations available. Run the pipeline first.")

    else:  # Summary
        with st.spinner("Loading summary..."):
            summary = api_call("/recommendations/summary")

        if summary:
            st.markdown("---")

            c1, c2 = st.columns(2)
            c1.metric("Total Recommendations", summary.get("total", 0))
            c2.metric("Total Cash Impact", f"${summary.get('total_cash_impact', 0):,.2f}")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("By Lever")
                by_lever = summary.get("by_lever", {})
                if by_lever:
                    lever_rows = []
                    for lever, vals in by_lever.items():
                        lever_rows.append({
                            "Lever": lever,
                            "Count": vals.get("count", 0),
                            "Cash Impact": vals.get("cash_impact", 0),
                        })
                    lever_df = pd.DataFrame(lever_rows)
                    st.dataframe(lever_df, use_container_width=True)
                    st.bar_chart(lever_df.set_index("Lever")[["Cash Impact"]])

            with col2:
                st.subheader("By Priority")
                by_pri = summary.get("by_priority", {})
                if by_pri:
                    pri_df = pd.DataFrame(
                        [(k, v) for k, v in by_pri.items()],
                        columns=["Priority", "Count"],
                    )
                    st.bar_chart(pri_df.set_index("Priority"))

    if show_metrics:
        st.markdown("---")
        st.subheader("RE Report")
        metrics = api_call("/recommendations/report")
        if metrics:
            st.dataframe(pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"]), use_container_width=True)
