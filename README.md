# Cash Flow Forecasting Platform

An enterprise-grade **cash flow forecasting and treasury intelligence platform** that combines machine learning, deterministic forecasting, and a recommendation engine to deliver accurate cash visibility and actionable financial insights.

Built based on **Cash Flow Solution Design Document (SDD v17)**.

---

## 🚀 Overview

This platform forecasts **cash inflows and outflows across 9 modules**, consolidates them into a **unified cash position**, and generates **data-driven treasury recommendations**.

It is designed for:
- Finance teams
- Treasury analysts
- CFO decision support systems

---

## 🧩 System Architecture

### Module Breakdown

| Module | Category | Technique | Description |
|--------|----------|----------|-------------|
| **S1** | ML Prediction | LightGBM + Random Forest | Predict AR invoice payment timelines |
| **S2** | ML Prediction | LightGBM + Random Forest | Predict AP bill payment adjustments |
| **Credit Risk** | ML Classification | LightGBM + RF | Customer risk segmentation |
| **S3** | Rule-Based | Deterministic | WIP / milestone billing forecasts |
| **S4** | Rule-Based | Cohort Matching | Sales pipeline cash projections |
| **S5** | Rule-Based | Scheduling | Contingent inflows (loans, refunds) |
| **S6** | Rule-Based | Category Logic | Expense forecasting |
| **S7** | Aggregation | Multi-step Pipeline | Unified cash position engine |
| **RE** | Intelligence | Scoring + Ranking | Treasury recommendations |

---

## 🔄 Data Flow Architecture

```mermaid
flowchart TD
    A[Raw Data Sources] --> B[Feature Store]

    B --> S1[AR Prediction]
    B --> S2[AP Prediction]
    B --> CR[Credit Risk]
    B --> S3[WIP Forecast]
    B --> S4[Pipeline Forecast]
    B --> S5[Contingent Inflows]
    B --> S6[Expense Forecast]

    S1 --> S7[Cash Aggregation]
    S2 --> S7
    CR --> S7
    S3 --> S7
    S4 --> S7
    S5 --> S7
    S6 --> S7

    S7 --> RE[Recommendation Engine]
    RE --> OUT[Cash Insights & Decisions]
````

---

## ⚡ Quick Start

### 1. Environment Setup

```bash
# Clone repository
cd Project-1

# Create virtual environment
python -m venv venv

# Activate environment
# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

### 2. Run Full Pipeline

```bash
python main.py
```

**Execution Flow:**

```
Feature Engineering → S1 → S2 → Credit Risk → S3 → S4 → S5 → S6 → S7 → Recommendations
```

---

### 3. Run Individual Modules

```bash
# Feature Engineering
python pipeline/run_feature_table.py

# ML Models
python pipeline/run_s1_ar_prediction.py
python pipeline/run_s2_ap_prediction.py
python pipeline/run_credit_risk.py

# Forecast Engines
python pipeline/run_s3_wip_forecast.py
python pipeline/run_s4_pipeline_forecast.py
python pipeline/run_s5_contingent_inflows.py
python pipeline/run_s6_expense_forecast.py

# Aggregation & Intelligence
python pipeline/run_s7_cash_aggregation.py
python pipeline/run_recommendation_engine.py
```

---

### 4. Launch Application

#### Backend (FastAPI)

```bash
python app/api.py
```

* API Base URL: `http://localhost:8000`
* Swagger Docs: `http://localhost:8000/docs`

#### Frontend (Streamlit)

```bash
streamlit run app/frontend.py
```

* UI: `http://localhost:8501`

---

### 5. MLflow Tracking

```bash
mlflow ui --backend-store-uri mlruns
```

* Dashboard: `http://localhost:5000`

---

## ⚙️ Configuration Management

The system is fully **config-driven** using YAML files.

### Core Configuration Files

| File                               | Purpose                            |
| ---------------------------------- | ---------------------------------- |
| `config.yml`                       | Global settings & pipeline control |
| `config/s1_ar_prediction.yml`      | AR model configuration             |
| `config/s2_ap_prediction.yml`      | AP model configuration             |
| `config/credit_risk.yml`           | Risk classification setup          |
| `config/s3_wip_forecast.yml`       | WIP forecasting rules              |
| `config/s4_pipeline_forecast.yml`  | Pipeline probability logic         |
| `config/s5_contingent_inflows.yml` | Inflow confidence mapping          |
| `config/s6_expense_forecast.yml`   | Expense modeling                   |
| `config/s7_cash_aggregation.yml`   | Aggregation logic                  |
| `config/recommendation_engine.yml` | Recommendation scoring             |

> ✅ No code changes required for tuning — update YAML configs only.

---

## 🔌 API Reference

### Prediction APIs

| Endpoint                             | Method | Description              |
| ------------------------------------ | ------ | ------------------------ |
| `/predict/s1/{invoice_id}`           | GET    | AR payment prediction    |
| `/predict/s1/new`                    | POST   | New AR prediction        |
| `/predict/s2/{bill_id}`              | GET    | AP adjustment prediction |
| `/predict/s2/new`                    | POST   | New AP prediction        |
| `/predict/credit_risk/{customer_id}` | GET    | Risk classification      |
| `/predict/credit_risk/new`           | POST   | New customer risk        |

---

### Forecast APIs

| Endpoint                        | Method | Description         |
| ------------------------------- | ------ | ------------------- |
| `/forecast/s3/{project_id}`     | GET    | WIP forecast        |
| `/forecast/s4/{opportunity_id}` | GET    | Pipeline forecast   |
| `/forecast/s5/records`          | GET    | Contingent inflows  |
| `/forecast/s6/records`          | GET    | Expense forecasts   |
| `/forecast/s7/daily`            | GET    | Daily cash position |
| `/forecast/s7/weekly`           | GET    | Weekly aggregation  |
| `/forecast/s7/monthly`          | GET    | Monthly aggregation |

---

### Recommendation APIs

| Endpoint                   | Method | Description              |
| -------------------------- | ------ | ------------------------ |
| `/recommendations`         | GET    | Ranked actions           |
| `/recommendations/summary` | GET    | Aggregated insights      |
| `/health`                  | GET    | System health check      |
| `/metrics/{model_key}`     | GET    | Model evaluation metrics |

---

## 🧠 Feature Store (Core Intelligence Layer)

A centralized feature store ensures **consistency, reusability, and scalability**.

| Table                     | Entity       | Update Frequency | Consumers      |
| ------------------------- | ------------ | ---------------- | -------------- |
| `customer_features`       | Customer     | Batch + Event    | S1, S3, S4, RE |
| `customer_payment_scores` | Customer     | Daily            | S1, S4, RE     |
| `invoice_features`        | Transactions | Daily            | S1             |
| `collections_features`    | Transactions | Real-time        | S1             |
| `vendor_features`         | Vendor       | Batch            | S2             |
| `bill_features`           | Transactions | Daily            | S2             |

---

## 📊 Output Schemas

### Payment Predictions

```
transaction_id, transaction_type, predicted_payment_date,
probability_buckets, expected_amount, confidence_tier, model_version
```

---

### Forecast Outputs

```
forecast_id, forecast_type, target_date,
forecast_amount, confidence_range,
source_module, run_id
```

---

## 🎯 Design Principles

* **Deterministic-first architecture**
* **Fully config-driven system**
* **Single source of truth (S7 layer)**
* **Auditability and traceability**
* **Shared feature store across models**
* **Explainable AI outputs**

---

## 🛠 Tech Stack

* **Machine Learning**: LightGBM, Scikit-learn
* **Backend**: FastAPI
* **Frontend**: Streamlit
* **Experiment Tracking**: MLflow
* **Data Processing**: Pandas, NumPy
* **Configuration**: YAML

---

## 📚 Documentation

| Document                       | Description        |
| ------------------------------ | ------------------ |
| `CashFlow_SDD_v17.docx`        | Full system design |
| `Model_InputOutput_Mapping.md` | Schema mapping     |
| `STRUCTURE.md`                 | Project structure  |

---

## ✅ Summary

This platform provides:

* End-to-end **cash flow visibility**
* Hybrid **ML + rule-based forecasting**
* Real-time **decision intelligence**
* Scalable, modular architecture for enterprise use

---

```
