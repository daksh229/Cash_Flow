# Cash Flow Forecasting Model

A comprehensive cash flow forecasting platform with ML prediction models, rule-based forecasting engines, and a recommendation engine for treasury decision-making.

Built from the **CashFlow Solution Design Document (SDD v17)**.

## Overview

The system predicts and forecasts cash inflows and outflows across 9 modules, aggregates them into a unified daily cash position, and generates actionable recommendations.

### Module Architecture

| Module | Type | Method | Purpose |
|--------|------|--------|---------|
| **S1** | Prediction (ML) | LightGBM + RF | Predict days_to_pay for AR invoices |
| **S2** | Prediction (ML) | LightGBM + RF | Predict payment timing for AP bills |
| **Credit Risk** | Classification (ML) | LightGBM + RF | Classify customers: LOW/MEDIUM/HIGH risk |
| **S3** | Forecast (Rule) | Deterministic | WIP/project milestone billing forecast |
| **S4** | Forecast (Rule) | Cohort matching | Sales pipeline cash forecast |
| **S5** | Forecast (Rule) | Scheduling | Contingent inflows (loans, grants, refunds) |
| **S6** | Forecast (Rule) | Category-based | Expense forecast (salary, tax, renewals) |
| **S7** | Aggregation | 9-step pipeline | Unified cash position with dedup |
| **RE** | Recommendation | Scoring + ranking | Actionable treasury recommendations |

### Data Flow

```
Raw Data (8 tables)
    |
    v
Feature Table (shared, computed once)
    |
    +---> S1 AR Prediction ----+
    +---> S2 AP Prediction ----+
    +---> Credit Risk ----------+
    +---> S3 WIP Forecast ------+---> S7 Cash Aggregation ---> Recommendation Engine
    +---> S4 Pipeline Forecast -+         |
    +---> S5 Contingent Inflows +         v
    +---> S6 Expense Forecast --+    Daily/Weekly/Monthly
                                     Cash Position
```

## Quick Start

### 1. Setup

```bash
# Clone and enter project
cd Project-1

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Full Pipeline

```bash
python main.py
```

This runs: Feature Table Generation --> S1 --> S2 --> Credit Risk --> S3 --> S4 --> S5 --> S6 --> S7 --> Recommendation Engine

### 3. Run Individual Modules

```bash
# Feature tables (required first)
python pipeline/run_feature_table.py

# Prediction models
python pipeline/run_s1_ar_prediction.py
python pipeline/run_s2_ap_prediction.py
python pipeline/run_credit_risk.py

# Forecast models
python pipeline/run_s3_wip_forecast.py
python pipeline/run_s4_pipeline_forecast.py
python pipeline/run_s5_contingent_inflows.py
python pipeline/run_s6_expense_forecast.py

# Aggregation + recommendations
python pipeline/run_s7_cash_aggregation.py
python pipeline/run_recommendation_engine.py
```

### 4. Web Application

```bash
# Terminal 1: FastAPI backend
python app/api.py
# API runs on http://localhost:8000
# Swagger docs at http://localhost:8000/docs

# Terminal 2: Streamlit frontend
streamlit run app/frontend.py
# UI runs on http://localhost:8501
```

### 5. MLflow Tracking

```bash
mlflow ui --backend-store-uri mlruns
# Dashboard at http://localhost:5000
```

## Configuration

All model parameters are config-driven via YAML files:

- **`config.yml`** - Master config: which models to run, global settings, MLflow
- **`config/s1_ar_prediction.yml`** - S1 hyperparams, features, encoding, eval metrics
- **`config/s2_ap_prediction.yml`** - S2 hyperparams, thin-data threshold
- **`config/credit_risk.yml`** - Classification settings, class imbalance handling
- **`config/s3_wip_forecast.yml`** - Milestone rules, completion threshold, invoice lag
- **`config/s4_pipeline_forecast.yml`** - Stage probabilities, cohort matching
- **`config/s5_contingent_inflows.yml`** - Confidence mapping by approval status
- **`config/s6_expense_forecast.yml`** - Confidence mapping by expense category
- **`config/s7_cash_aggregation.yml`** - Source trust hierarchy, dedup rules, opening balance
- **`config/recommendation_engine.yml`** - Scoring weights, lever configs, constraints

To change hyperparameters, edit the YAML - no code changes needed.

## API Endpoints

### Prediction Models (Dual Mode: Lookup + New Entry)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict/s1/{invoice_id}` | GET | Predict days_to_pay for existing invoice |
| `/predict/s1/new` | POST | Predict for new invoice (raw inputs) |
| `/predict/s2/{bill_id}` | GET | Predict adjustment_delta for existing bill |
| `/predict/s2/new` | POST | Predict for new bill |
| `/predict/credit_risk/{customer_id}` | GET | Classify existing customer risk |
| `/predict/credit_risk/new` | POST | Classify new customer |

### Forecast Models

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/forecast/s3/{project_id}` | GET | S3 WIP forecast for a project |
| `/forecast/s4/{opportunity_id}` | GET | S4 pipeline forecast for a deal |
| `/forecast/s5/records` | GET | All S5 contingent inflow records |
| `/forecast/s6/records` | GET | All S6 expense records |
| `/forecast/s7/daily` | GET | S7 daily cash position |
| `/forecast/s7/weekly` | GET | S7 weekly aggregation |
| `/forecast/s7/monthly` | GET | S7 monthly aggregation |

### Recommendations & Utilities

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/recommendations` | GET | All ranked recommendations |
| `/recommendations/summary` | GET | Summary by lever and priority |
| `/lookup/invoices\|bills\|customers\|projects\|deals` | GET | List available IDs |
| `/health` | GET | API health + loaded models |
| `/metrics/{model_key}` | GET | Evaluation metrics for a model |

## Central Financial Intelligence Layer

The system is built around a shared **Feature Store** with 6 tables:

| Table | Entity | Updated | Consumed By |
|-------|--------|---------|-------------|
| `customer_features` | Customer | Nightly + Event | S1, S3, S4, RE, Credit Risk |
| `customer_payment_scores` | Customer | Nightly | S1, S4, RE, Credit Risk |
| `invoice_features` | Transaction | Daily + Event | S1, RE |
| `collections_features` | Transaction | Event | S1, RE |
| `vendor_features` | Vendor | Nightly + Event | S2, RE |
| `bill_features` | Transaction | Daily + Event | S2 |

All models read from this shared store. No module computes features independently.

## Output Tables

Two standardised output schemas (from the SDD):

### payment_predictions (S1, S2)
```
transaction_id, transaction_type (AR/AP), predicted_payment_date,
baseline_predicted_date, prob_pay_0_30, prob_pay_30_60, prob_pay_60_plus,
expected_payment_amount, trigger_event, confidence_tier, prediction_date, model_version
```

### forecast_outputs (S1-S7)
```
forecast_id, forecast_date, forecast_type (AR/AP/WIP/PIPELINE/INFLOW/EXPENSE/CASH),
target_date, forecast_amount, confidence_low, confidence_high,
source_module (S1-S7), forecast_run_id
```

## Design Principles

- **Deterministic first** - Phase 1 prioritises auditability; ML is additive
- **Config-driven** - All parameters in YAML; no hardcoded values
- **Single source of truth** - S7 is the only view downstream consumers read
- **Non-destructive** - Suppressed events retained with reason codes
- **Shared Feature Store** - All models consume the same versioned features
- **Explainable** - Every recommendation states what, why, entity, and cash impact

## Tech Stack

- **ML**: LightGBM, scikit-learn (Random Forest)
- **Tracking**: MLflow
- **Backend**: FastAPI + Uvicorn
- **Frontend**: Streamlit
- **Config**: YAML (PyYAML)
- **Data**: pandas, numpy

## Document Reference

- **SDD**: `CashFlow_SDD_v17-20032026.docx` - Full solution design
- **Schema**: `Model_InputOutput_Mapping.md` - Input/output field-level mappings
- **Structure**: `STRUCTURE.md` - Complete file tree with descriptions
