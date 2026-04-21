# steps/credit_risk/

**Credit Risk Assessment.** Classifies each customer as LOW / MEDIUM / HIGH risk using only `customer_features`. The output feeds the recommendation engine's risk-reduction scoring component.

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads `customer_features` + target column `risk_segment` from `customer_payment_scores`. |
| `preprocessing.py` | 2 | Encodes target (LOW=0, MEDIUM=1, HIGH=2). Stratified 80/20 split. Handles class imbalance via sample weights. |
| `model_training.py` | 3 | Trains LightGBM multiclass + Random Forest baseline with `class_weight="balanced"`. CV F1-macro. |
| `evaluate.py` | 4 | Accuracy, F1 (macro + per class), confusion matrix, AUC-ROC (OvR). Saves metrics report. |
| `__init__.py` | — | Package marker. |

## Config

[config/credit_risk.yml](../../config/credit_risk.yml):
- `features.*`, model hyperparams.
- `split.method = stratified` (mandatory due to class imbalance — HIGH is ~5% of data).
- Class encoding mapping.

## Run individually

```bash
python pipeline/run_credit_risk.py
```

## Role in orchestration pipeline

Runs in parallel with S1/S2/S3/S4 after `feature_table`. Has no downstream consumer until the recommendation engine reads the latest risk prediction per customer.

**Known issue on synthetic data:** CV F1-macro of 0.98+ is suspiciously high — likely target leakage from one of the aggregate features into `risk_segment` (both are derived from the same `customer_payment_scores` source). To be investigated once real data lands.

## Related

- Consumer: [steps/recommendation_engine/](../recommendation_engine/) (risk-reduction scoring component).
- Shared helpers: [steps/shared/](../shared/).
