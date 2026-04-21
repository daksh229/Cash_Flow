"""
Model Dependency Graph
======================
Declares the producer/consumer relationships between the pipeline's models.
The DAG uses this to order execution and to know what to re-run when an
upstream module's output changes.

Edges reflect the SSD data flow:
  - feature_table feeds every ML model
  - S7 aggregates S1..S6
  - recommendation_engine reads S7 + predictions
"""

MODEL_DEPENDENCIES = {
    "feature_table":          [],
    "s1_ar_prediction":       ["feature_table"],
    "s2_ap_prediction":       ["feature_table"],
    "credit_risk":            ["feature_table"],
    "s3_wip_forecast":        ["feature_table"],
    "s4_pipeline_forecast":   ["feature_table"],
    "s5_contingent_inflows":  [],
    "s6_expense_forecast":    [],
    "s7_cash_aggregation":    [
        "s1_ar_prediction",
        "s2_ap_prediction",
        "s3_wip_forecast",
        "s4_pipeline_forecast",
        "s5_contingent_inflows",
        "s6_expense_forecast",
    ],
    "recommendation_engine":  ["s7_cash_aggregation", "credit_risk"],
}
