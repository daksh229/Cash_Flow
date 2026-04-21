"""
Streamlit form - Non-PO Expense capture
=======================================
Standalone page users can launch or wire into app/frontend.py.

    streamlit run app/pages/non_po_expense_form.py

Expects the API base URL in env var CASHFLOW_API_URL (default
http://localhost:8000) and a bearer token in CASHFLOW_TOKEN.
"""

import os
from datetime import date, datetime

import requests
import streamlit as st

API_URL = os.environ.get("CASHFLOW_API_URL", "http://localhost:8000")
TOKEN = os.environ.get("CASHFLOW_TOKEN", "")
TENANT = os.environ.get("CASHFLOW_TENANT_ID", "default")

st.set_page_config(page_title="Non-PO Expense", page_icon="💸")
st.title("Capture Non-PO Expense")
st.caption("Expenses that never went through a purchase order — "
           "legal, ad-hoc travel, consultancy, ads, etc.")

with st.form("non_po"):
    category = st.selectbox(
        "Category",
        ["Salary", "Tax", "Rent", "Legal", "Ad", "Travel", "Consultancy", "Other"],
    )
    description = st.text_area("Description", max_chars=500)
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f")
        currency = st.selectbox("Currency", ["INR", "USD", "EUR", "GBP"])
    with col2:
        expected = st.date_input("Expected payment date", value=date.today())
        confidence = st.slider("Confidence", 0.0, 1.0, 0.8, step=0.05)
    recurrence = st.selectbox("Recurrence", ["none", "monthly", "quarterly"])
    submitted = st.form_submit_button("Submit")

if submitted:
    if amount <= 0:
        st.error("Amount must be positive.")
        st.stop()
    payload = {
        "category": category,
        "description": description or None,
        "amount": float(amount),
        "currency": currency,
        "expected_date": datetime.combine(expected, datetime.min.time()).isoformat(),
        "confidence": confidence,
        "recurrence": recurrence,
    }
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Tenant-Id": TENANT,
    }
    try:
        r = requests.post(f"{API_URL}/expenses/non-po", json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        st.error(f"Network error: {e}")
    else:
        if r.status_code == 201:
            st.success(f"Recorded expense #{r.json()['id']}")
        else:
            st.error(f"API returned {r.status_code}: {r.text}")

st.divider()
st.subheader("Active Non-PO expenses")
try:
    r = requests.get(
        f"{API_URL}/expenses/non-po",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Tenant-Id": TENANT},
        timeout=10,
    )
    if r.ok:
        st.dataframe(r.json(), use_container_width=True)
    else:
        st.warning(f"Could not fetch list (HTTP {r.status_code}).")
except requests.RequestException:
    st.info("API not reachable. Start it with `python app/api.py`.")
