# Cash Flow Forecasting Model - Input/Output Mapping

## Model Architecture Table

| **Type** | **Static Input** | **Derived Input** | **Output** | **Output Datatype** | **Description** |
|---------|------------------|-------------------|-----------|-------------------|-----------------|
| **AR Collections Forecast (S1)** | invoice_features + customer_features + collections_features | customer_payment_scoring_from_features | payment_predictions (AR) | Table | Contains predicted payment dates, probability buckets (0-30, 30-60, 60+ days), expected payment amounts, confidence tiers (HIGH/MEDIUM/LOW), trigger events, and baseline comparison dates from Random Forest model |
| **AP Payment Forecast (S2)** | vendor_features + bill_level_features | vendor_payment_patterns_computed | payment_predictions (AP) | Table | Vendor-specific payment forecasts with predicted payment dates, probability distributions across time buckets, expected settlement amounts, and confidence tiers for AP obligations |
| **WIP Billing Forecast (S3)** | customer_features (AR avg delay metric) | wip_to_invoice_conversion_rate | forecast_outputs (WIP type) | Table | Work-in-progress billing forecasts with target dates, forecast amounts, confidence ranges (low/high), source module reference (S3), and forecast run tracking for service delivery cycles |
| **Pipeline Forecast (S4)** | customer_features (AR avg delay + risk_segment) | pipeline_stage_conversion_probability | forecast_outputs (PIPELINE type) | Table | Sales pipeline to cash conversion forecasts with target dates, forecast amounts, confidence intervals, source module (S4), run ID, and risk-segment adjusted probabilities for deal closure |
| **Expense Forecast (S5)** | operational_expense_features | recurring_vs_onetime_classification | forecast_outputs (EXPENSE type) | Table | Operational expense forecasts with scheduled payment dates, forecast amounts, confidence bounds, categorization by expense type, and source module (S5) tracking for budget planning |
| **Other Cash Movements (S6)** | miscellaneous_cash_features | manual_adjustment_factors | forecast_outputs (CASH type - Other) | Table | Ad-hoc and unclassified cash movement forecasts including adjustments, refunds, reversals with target dates, amounts, confidence levels, and source module (S6) reference for residual cash flows |
| **Cash Forecast Aggregation (S7)** | All forecast_outputs (AR+AP+WIP+PIPELINE+EXPENSE+S6) | daily_net_position_calculation | forecast_outputs (CASH type) + Daily Position Summary | Table + Float | Aggregated cash forecast combining all modules (S1-S6) with daily net inflow/outflow positions, cumulative cash balance projections, consolidated confidence ranges, and forecast_run_id for end-to-end traceability |
| **Credit Risk Assessment** | customer_features (dispute_ratio + payment_volatility + DSO) | payment_behavior_volatility_score | customer_payment_scores | Enum (HIGH/MEDIUM/LOW) | Risk segment classification for each customer based on historical payment behavior, dispute patterns, days sales outstanding, and volatility metrics to guide collections prioritization and credit decisions |
| **Collections Prioritisation** | customer_payment_scores + collections_features + invoice_features | priority_scoring_algorithm | payment_predictions (ranking + days_overdue + prob_buckets) | JSON | Ranked collection priorities with invoice-level overdue days, probability of payment within each time bucket (0-30, 30-60, 60+), and recommended action severity for collections team workflow |
| **Recommendation Engine** | customer_payment_scores + collections_features + vendor_features | recommendation_confidence_calculation | payment_predictions + forecast_outputs + recommended_actions | JSON | Actionable recommendations for collections, credit, and cash management including: suggested collection actions, customer segment strategies, payment terms optimization, and cash timing alerts with confidence scores |

---

## Key Definitions

### Input Classifications:
- **Static Input**: Core feature tables and datasets (customer_features, invoice_features, vendor_features, collections_features)
- **Derived Input**: Computed features and intermediate outputs (scoring algorithms, conversion rates, volatility calculations)

### Output Datatypes:
- **Table**: Multi-row, multi-column data structure (typically stored in database/data lake)
- **Float**: Numeric value with decimal precision
- **Enum**: Predefined categorical values (e.g., HIGH/MEDIUM/LOW)
- **JSON**: Complex nested structure for recommendations and configurations

### Module Pipeline:
```
Static Features → S1-S6 (Parallel Forecasting) → S7 (Aggregation) → Credit Risk + Collections + Recommendations
```

---

## Output Table Schema Reference

### payment_predictions Table Fields:
- predicted_payment_date (Date)
- baseline_predicted_date (Date)
- prob_pay_0_30 (Float: 0-1)
- prob_pay_30_60 (Float: 0-1)
- prob_pay_60_plus (Float: 0-1)
- expected_payment_amount (Float)
- trigger_event (String)
- confidence_tier (Enum: HIGH/MEDIUM/LOW)
- prediction_date (Timestamp)
- model_version (String)

### forecast_outputs Table Fields:
- forecast_id (String: UUID)
- forecast_date (Date)
- forecast_type (Enum: AR/AP/WIP/PIPELINE/EXPENSE/CASH)
- target_date (Date)
- forecast_amount (Float)
- confidence_low (Float)
- confidence_high (Float)
- source_module (Enum: S1-S7)
- forecast_run_id (UUID)

---

## Feature Store Tables — Detailed Schema

The Central Financial Intelligence Layer maintains 6 core feature tables. All forecasting modules (S1-S7) and the Recommendation Engine read from these tables at runtime rather than recomputing from raw data. Each table is versioned and timestamped for auditability.

### 1. customer_features
**Update Frequency**: Nightly batch + Event-driven triggers | **Purpose**: Shared customer payment behavior across all modules  
**Consumed by**: S1 (AR prediction), S3 (WIP billing), S4 (pipeline), RE (recommendations), Credit Risk

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| customer_id | String | Key | Unique customer identifier (FK → customers) |
| feature_date | Date | Nightly | Snapshot date for this feature version (enables historical tracking) |
| avg_payment_delay | Float | Nightly | Average days late across all historical invoices |
| median_payment_delay | Float | Nightly | Median delay (less sensitive to outliers than mean) |
| late_payment_ratio | Float | Nightly | Fraction of invoices paid after due date (0.0-1.0) |
| payment_volatility | Float | Nightly | Std dev of days_to_pay — high value = unpredictable payer |
| dispute_ratio | Float | Nightly | Fraction of invoices that had a dispute raised |
| ptp_kept_ratio | Float | Event | Of all promises-to-pay made, fraction actually honoured |
| recent_reminder_velocity | Integer | Event | Reminders sent across all open invoices in last 14 days — rising trend signals relationship deterioration |
| open_dispute_count | Integer | Event | Currently active disputes across all invoices for this customer (escalation signal) |
| days_since_last_payment | Integer | Event | Days since most recent cash receipt — recency indicator of customer engagement |
| payment_trend_30d | Float | Event | 30-day rolling delta of actual days_to_pay vs. long-run average. Positive values indicate worsening trend. |
| days_sales_outstanding | Float | Nightly | DSO metric: outstanding AR / (trailing 12m revenue / 365) |
| seasonality_index | Float | Nightly | Customer-level seasonal payment pattern index (0.5-2.0) — captures month-of-year payment speed multiplier |
| avg_invoice_amount | Float | Nightly | Average invoice value for this customer |
| invoice_count | Integer | Nightly | Total historical invoices — used as reliability proxy (thin-data check at < 10 invoices) |
| non_invoice_payment_count | Integer | Event | Count of advance/retainer/direct transfer receipts from this customer — indicator of relationship maturity |
| advance_payment_ratio | Float | Event | Fraction of total cash received from this customer that arrived before invoice issuance |
| feature_version | String | On change | Version tag of feature logic that produced this row — enables drift detection and retraining |

---

### 2. customer_payment_scores
**Update Frequency**: Nightly batch (Customer Behaviour Model output) | **Purpose**: Pre-computed reliability scores shared across S1, S4, Recommendation Engine, Credit Risk  
**Layer**: Prediction Store — Layer 1 output consumed as feature input to all downstream predictions

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| customer_id | String | Key | Customer reference (FK → customers) |
| payment_score | Float | Nightly | Overall reliability index (0.0-1.0): 1.0 = always pays on time, 0.0 = chronic late payer |
| expected_delay | Float | Nightly | Model-predicted average days late for next invoice at this customer's current scoring date |
| risk_segment | Enum | Nightly | Categorical risk classification: LOW / MEDIUM / HIGH — shared across S1, S4, RE, and credit risk module |
| score_date | Date | Nightly | Date this score was computed (enables point-in-time analysis) |
| model_version | String | On retrain | Customer Behaviour Model version — enables pre/post retraining comparison and audit trail |

---

### 3. invoice_features
**Update Frequency**: Daily batch + Event-driven (on each invoice lifecycle trigger) | **Purpose**: Transaction-level AR invoice attributes and lifecycle signals  
**Consumed by**: S1 (per-invoice prediction), Recommendation Engine (collections prioritization)

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| invoice_id | String | Key | Unique invoice reference (FK → invoices) |
| customer_id | String | Static | Customer reference (FK → customers, links to customer_features) |
| invoice_date | Date | Static | Date invoice was raised (used in days_to_pay calculation) |
| due_date | Date | Static | Contractual payment due date |
| invoice_amount | Float | Static | Invoice value in base currency |
| invoice_age_days | Integer | Daily | Computed: today − invoice_date (days since issuance) |
| days_past_due | Integer | Daily | Computed: today − due_date (floor 0 if not yet overdue) — escalation trigger signal |
| invoice_amount_bucket | Enum | Static | SMALL / MEDIUM / LARGE — classification relative to customer history |
| amount_percentile_customer | Float | Static | This invoice amount as percentile (0.0-1.0) of this customer's historical invoice distribution |
| payment_terms | String | Static | Payment terms (NET30, NET60, etc.) — used for due date computation |
| dispute_flag | Boolean | Event | Whether a dispute is currently open on this invoice (risk signal) |
| partial_payment_flag | Boolean | Event | Whether a partial payment has been received (lifecycle status) |
| partial_payment_amount | Float | Event | Amount paid to date (0 if none) |
| feature_date | Date | Daily | Snapshot date of this feature row — enables version control and historical playback |

---

### 4. collections_features
**Update Frequency**: Event-driven (on each collections interaction) + Derived nightly | **Purpose**: Collections engagement history and commitment signals at invoice level  
**Consumed by**: S1 (feature input for prediction), Recommendation Engine (ranking logic), Collections team

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| invoice_id | String | Key | Invoice reference (FK → invoices, links to invoice_features) |
| reminder_count | Integer | Event | Total reminders sent for this invoice (engagement intensity signal) |
| call_count | Integer | Event | Total calls made for this invoice (collection effort indicator) |
| promise_to_pay_flag | Boolean | Event | Whether a PTP commitment has been given for this invoice (strong signal) |
| promise_to_pay_date | Date | Event | Customer-committed payment date (if PTP given, null otherwise) — used as prediction anchor |
| days_since_last_contact | Integer | Event | Days since most recent collections interaction on this invoice (recency signal) |
| ptp_kept_ratio_customer | Float | Event | Of the last 5 PTPs made by this customer, fraction honoured — recency-weighted reliability of commitment |
| escalation_status | Enum | Event | Current escalation level: NONE / REMINDER / FORMAL / LEGAL — determines next action severity |

---

### 5. vendor_features
**Update Frequency**: Nightly batch + Event-driven triggers | **Purpose**: Shared vendor payment behavior and patterns across S2 (Vendor Payment Forecast) and Recommendation Engine  
**Consumed by**: S2 (AP payment prediction), Recommendation Engine (vendor prioritization logic)

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| vendor_id | String | Key | Unique vendor identifier (FK → vendors) |
| feature_date | Date | Nightly | Snapshot date for this feature version (versioning for historical tracking) |
| avg_payment_cycle_days | Float | Nightly | Average days we take to pay this vendor from invoice receipt — primary anchor for payment timing |
| payment_volatility | Float | Nightly | Std dev of our payment cycle for this vendor — high volatility = less predictable actual payment date |
| discount_capture_ratio | Float | Nightly | Fraction of available early-payment discounts we have historically captured from this vendor |
| late_payment_ratio | Float | Nightly | Fraction of invoices we paid late to this vendor (after contractual due date) |
| vendor_chase_frequency | Integer | Event | How often this vendor follows up on unpaid invoices per month — signal of their payment pressure |
| avg_invoice_amount | Float | Nightly | Average AP invoice value for this vendor — large invoices tend to be paid more carefully |
| invoice_count | Integer | Nightly | Total historical invoices to this vendor — thin-data threshold check (fallback to category average if < 10) |
| last_payment_date | Date | Event | Date of most recent payment made to this vendor (recency of relationship activity) |
| po_to_bill_lag | Float | Nightly | Average days from PO creation to bill receipt — forecasts when committed obligations convert to payables |
| advance_payment_ratio | Float | Event | Fraction of our payments to this vendor that were made in advance of bill receipt (relationship pattern) |
| feature_version | String | On change | Feature logic version — enables drift detection and compatibility checking |

---

### 6. bill_features
**Update Frequency**: Daily batch + Event-driven (on each bill lifecycle event) | **Purpose**: Transaction-level AP bill attributes and payment readiness signals  
**Consumed by**: S2 (per-bill payment prediction), Vendor prioritization logic

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| bill_id | String | Key | Unique AP bill identifier (FK → bills) |
| vendor_id | String | Static | Vendor reference (FK → vendors, links to vendor_features) |
| feature_date | Date | Daily | Snapshot date of this feature row (versioning for historical playback) |
| bill_age_days | Integer | Daily | Computed: today − bill_date (days since bill was received) |
| days_past_due | Integer | Daily | Computed: today − due_date (floor 0 if not yet due) — used for late payment penalty calculations |
| bill_amount | Float | Static | Bill value in base currency |
| bill_amount_bucket | Enum | Static | SMALL / MEDIUM / LARGE — classification relative to vendor average (payment care indicator) |
| amount_percentile_vendor | Float | Static | Bill amount as percentile (0.0-1.0) of this vendor's historical bills |
| approval_status | Enum | Event | PENDING / APPROVED — payment not scheduled until APPROVED status reached |
| early_payment_eligible | Boolean | Event | True if within the early payment discount window (NPV calculation trigger) |
| penalty_accruing | Boolean | Event | True if past due and a late payment penalty applies (cost-benefit factor in S2) |

---

---

### 7. collections_events (Raw Event Log)
**Update Frequency**: Real-time (as interactions occur) | **Purpose**: Raw transaction log of all collections activities — feeds aggregation into collections_features  
**Role**: Source-of-truth event log; collections_features are derived nightly from this table

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| event_id | String | Real-time | Unique event identifier (UUID) |
| invoice_id | String | Real-time | Invoice this event relates to (FK → invoices, links to collections_features) |
| customer_id | String | Real-time | Customer reference (FK → customers) |
| event_type | Enum | Real-time | REMINDER / CALL / PTP / DISPUTE / PARTIAL_PAYMENT / INVOICE_VIEWED / ESCALATION — interaction type |
| event_date | Timestamp | Real-time | Timestamp of the interaction (precise timing for sequencing) |
| promise_to_pay_date | Date | Real-time | Customer-committed payment date (PTP events only, null otherwise) |
| collector_id | String | Real-time | Collections rep who logged the interaction (audit trail) |
| event_notes | Text | Real-time | Free-text notes (optional) — rich data for manual review but not directly used as model feature |

---

### 8. purchase_orders
**Update Frequency**: Event-driven (on PO approval) | **Purpose**: Captures committed AP obligations before bill receipt — enables earlier visibility of future cash outflows  
**Role**: Bridges PO commitment → Bill receipt → Payment (closure of obligation lifecycle)  
**Consumed by**: S2 (vendor payment forecast), S6 (expense forecast), vendor_features computation

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| po_id | String | Key | Unique purchase order identifier |
| vendor_id | String | Static | Vendor reference (FK → vendors) — links to vendor_features |
| po_date | Date | Static | Date PO was raised and approved (commitment date) |
| po_amount | Float | Static | Committed spend value in base currency |
| expected_invoice_date | Date | Static | Expected date the vendor will raise a bill against this PO — informs invoice lag estimation |
| po_status | Enum | Event | OPEN / PARTIALLY_BILLED / FULLY_BILLED / CANCELLED — tracks lifecycle from commitment to completion |
| po_category | String | Static | Expense category (IT, Services, Materials, etc.) — used for S6 expense classification and trend analysis |

**Note**: Without purchase_orders, S2 cannot forecast vendor payment dates until bills arrive. po_to_bill_lag computed from this table enables S6 to schedule outflows at PO commitment time, providing critical early warning of cash needs.

---

### 9. non_invoice_payments
**Update Frequency**: Event-driven (as payments post) | **Purpose**: Captures all cash movements NOT originating from linked AR invoices or AP bills  
**Role**: Closes the gap between ERP documents and actual bank movements; ensures complete behavioral signals  
**Critical for**: Feature store completeness; without this, customer_features.advance_payment_ratio and cash forecasts have unexplained variances

| Field | Datatype | Update Cadence | Description |
|-------|----------|----------------|-------------|
| payment_id | String | Key | Unique identifier for this non-standard payment |
| party_id | String | Event | customer_id or vendor_id — the counterparty (FK → customers or vendors) |
| party_type | Enum | Event | CUSTOMER or VENDOR — identifies which party this payment involves |
| payment_type | Enum | Event | ADVANCE / RETAINER / REFUND / DIRECT_TRANSFER / BANK_CREDIT / TAX_REFUND / OTHER — classification of payment purpose |
| direction | Enum | Event | INFLOW or OUTFLOW — from our perspective |
| amount | Float | Event | Amount in base currency (always positive; use direction field to determine flow direction) |
| payment_date | Date | Event | Date cash actually moved (determines forecast position impact date) |
| payment_method | Enum | Event | BANK_TRANSFER / CHEQUE / ACH / CARD / OTHER — settlement mechanism |
| linked_document_id | String | Event | Optional reference to a future invoice, PO, or contract if one exists (null if completely ad-hoc) |
| notes | Text | Event | Free-text description — important for reconciliation audit and exception handling |

**Examples of what this captures**: Customer advances before invoice issuance, vendor retainers, refunds (credit notes settled as cash), advance payments to vendors pre-bill, direct bank transfers with no document reference, bank credits, interest receipts, FX settlements, tax refunds.

**Impact on Feature Store**: 
- Feeds customer_features.advance_payment_ratio (relationship maturity indicator)
- Feeds customer_features.non_invoice_payment_count (engagement signal)
- Feeds vendor_features.advance_payment_ratio (payment discipline pattern)
- Without this table, S7 cash event normalisation has unexplained inflows/outflows

---

**Feature Store Architecture Principle**: The platform is built around three financial intelligence entities (Customer, Vendor, Transaction). Features are centralized in this store — no module maintains isolated feature tables. This eliminates duplication, ensures consistency, and makes the entire system's behavioural foundation traceable and auditable.

---

**Document Version**: CashFlow_SDD_v17 | **Date**: March 20, 2026
