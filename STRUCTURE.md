# Project Structure

```
Project-1/
|
|-- main.py                              # Entry point - reads config.yml, orchestrates full pipeline
|-- config.yml                           # Master config - models to run, global settings, MLflow
|-- requirements.txt                     # Python dependencies
|-- .gitignore                           # Git ignore rules
|
|-- config/                              # Per-model configuration (YAML)
|   |-- s1_ar_prediction.yml             # S1: features, hyperparams, encoding, split, eval settings
|   |-- s2_ap_prediction.yml             # S2: vendor/bill features, hyperparams, thin-data threshold
|   |-- credit_risk.yml                  # Credit Risk: classification config, class imbalance
|   |-- s3_wip_forecast.yml              # S3: milestone rules, invoice lag, completion threshold
|   |-- s4_pipeline_forecast.yml         # S4: stage probabilities, cohort matching, invoice lag
|   |-- s5_contingent_inflows.yml        # S5: confidence mapping by approval status
|   |-- s6_expense_forecast.yml          # S6: confidence mapping by category
|   |-- s7_cash_aggregation.yml          # S7: source trust, dedup rules, opening balance
|   |-- recommendation_engine.yml        # RE: scoring weights, lever configs, constraints
|
|-- steps/                               # Core pipeline logic
|   |-- feature_table.py                 # COMMON: builds all 6 feature tables from raw data
|   |
|   |-- s1_ar_prediction/               # S1 - AR Collections Prediction (ML)
|   |   |-- input_format.py             #   Merges invoice + customer + collections + scores
|   |   |-- preprocessing.py            #   Derives days_to_pay target, encodes, splits
|   |   |-- model_training.py           #   LightGBM + Random Forest regression, MLflow
|   |   |-- evaluate.py                 #   Metrics, accuracy, saves payment_predictions + forecast_outputs
|   |
|   |-- s2_ap_prediction/               # S2 - AP Payment Prediction (ML)
|   |   |-- input_format.py             #   Merges vendor + bill features
|   |   |-- preprocessing.py            #   Derives adjustment_delta target, encodes, splits
|   |   |-- model_training.py           #   LightGBM + Random Forest regression, MLflow
|   |   |-- evaluate.py                 #   Metrics, thin-data analysis, saves payment_predictions
|   |
|   |-- credit_risk/                     # Credit Risk Assessment (ML Classification)
|   |   |-- input_format.py             #   Loads customer_features + risk_segment target
|   |   |-- preprocessing.py            #   Encodes target, stratified split, class imbalance
|   |   |-- model_training.py           #   LightGBM + RF classifier, class weights, MLflow
|   |   |-- evaluate.py                 #   Accuracy, F1, confusion matrix, AUC-ROC
|   |
|   |-- s3_wip_forecast/                # S3 - WIP Billing Forecast (Rule-based)
|   |   |-- input_format.py             #   Loads milestones + customer payment delays
|   |   |-- forecast_engine.py          #   5-step rule pipeline: completion -> invoice -> cash date
|   |   |-- output.py                   #   Saves forecast + summary report
|   |
|   |-- s4_pipeline_forecast/           # S4 - Sales Pipeline Forecast (Rule-based)
|   |   |-- input_format.py             #   Loads CRM deals + customer delays + cohort stats
|   |   |-- forecast_engine.py          #   Stage probability x milestone extrapolation
|   |   |-- output.py                   #   Saves detailed + unified forecast_outputs
|   |
|   |-- s5_contingent_inflows/          # S5 - Contingent Inflows (Deterministic)
|   |   |-- input_format.py             #   Loads loans, grants, refunds, insurance
|   |   |-- forecast_engine.py          #   Applies receipt lag, confidence by approval status
|   |   |-- output.py                   #   Saves forecast + summary
|   |
|   |-- s6_expense_forecast/            # S6 - Expense Forecast (Category-based Scheduling)
|   |   |-- input_format.py             #   Loads expense schedule (salary, tax, PO, renewals)
|   |   |-- forecast_engine.py          #   Applies payment lag, confidence by category
|   |   |-- output.py                   #   Saves forecast (outflows as negative amounts)
|   |
|   |-- s7_cash_aggregation/            # S7 - Cash Event Normalisation (Aggregation Engine)
|   |   |-- input_format.py             #   Ingests all S1-S6 outputs, standardises schema
|   |   |-- forecast_engine.py          #   Dedup, aggregate daily/weekly/monthly, cumulative balance
|   |   |-- output.py                   #   Saves event store, time-series, cash forecast
|   |
|   |-- recommendation_engine/          # Recommendation Engine (Scoring + Ranking)
|       |-- input_format.py             #   Loads S7 position, predictions, overdue invoices
|       |-- forecast_engine.py          #   Scenario generation, scoring, ranking
|       |-- output.py                   #   Saves ranked recommendations
|
|-- pipeline/                            # Pipeline runners (standalone or via main.py)
|   |-- run_all.py                       # Master orchestrator
|   |-- run_feature_table.py             # Runs common feature table generation
|   |-- run_s1_ar_prediction.py          # Runs S1 full pipeline (4 steps)
|   |-- run_s2_ap_prediction.py          # Runs S2 full pipeline (4 steps)
|   |-- run_credit_risk.py               # Runs Credit Risk pipeline (4 steps)
|   |-- run_s3_wip_forecast.py           # Runs S3 forecast (3 steps)
|   |-- run_s4_pipeline_forecast.py      # Runs S4 forecast (3 steps)
|   |-- run_s5_contingent_inflows.py     # Runs S5 forecast (3 steps)
|   |-- run_s6_expense_forecast.py       # Runs S6 forecast (3 steps)
|   |-- run_s7_cash_aggregation.py       # Runs S7 aggregation (3 steps)
|   |-- run_recommendation_engine.py     # Runs Recommendation Engine (3 steps)
|
|-- app/                                 # Web Application
|   |-- api.py                           # FastAPI backend (dual mode: lookup + new entry)
|   |-- frontend.py                      # Streamlit frontend (all 9 models + dashboard)
|
|-- sample_data/                         # Data generation scripts + reference CSVs
|   |-- generate_raw_tables.py           # Generates 8 base financial tables
|   |-- generate_customer_data.py
|   |-- generate_invoice_data.py
|   |-- generate_vendor_data.py
|   |-- generate_remaining_data.py
|   |-- generate_project_milestones.py   # Generates project milestone data for S3
|   |-- generate_crm_pipeline.py         # Generates CRM pipeline data for S4
|   |-- generate_s5_s6_data.py           # Generates contingent inflows + expense schedule
|
|-- CashFlow_SDD_v17-20032026.docx       # Solution Design Document (source of truth)
|-- Model_InputOutput_Mapping.md         # Model input/output schema reference
|
|-- [GENERATED AT RUNTIME - git ignored]
|-- Data/features/                       # Computed feature tables (6 CSVs)
|-- Data/forecast_outputs/               # All module outputs + S7 aggregated views
|-- models/                              # Trained model binaries (.pkl)
|-- reports/                             # Evaluation metrics and summaries
|-- mlruns/                              # MLflow experiment tracking data
```
