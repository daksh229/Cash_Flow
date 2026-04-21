# tests/regression/

Metric-drift gate. Compares the latest metric snapshot against committed baselines. Fails when a metric regresses beyond tolerance.

## Files

| File | Purpose |
|------|---------|
| `baselines.yml` | Last-known-good metrics per model with `value`, `tolerance`, `direction` (`higher_is_better` or `lower_is_better`). Updated **deliberately** by a human when a genuine improvement ships. |
| `test_metric_baselines.py` | Parametric test over `(model_key, metric_name)`. Reads the latest `reports/<model>*metrics*.json`; skips if no file yet; fails if the value is worse than `baseline ± tolerance`. |
| `__init__.py` | Package marker. |

## Current baselines

| Model / metric | Value | Tolerance | Direction |
|----------------|-------|-----------|-----------|
| `s1_ar_prediction.test_mae` | 6.5 | 1.0 | lower |
| `s1_ar_prediction.test_r2` | 0.72 | 0.05 | higher |
| `s2_ap_prediction.test_mae` | 2.1 | 0.5 | lower |
| `credit_risk.test_f1` | 0.80 | 0.03 | higher |
| `credit_risk.test_accuracy` | 0.83 | 0.03 | higher |
| `s7_cash_aggregation.dedup_rate` | 0.98 | 0.02 | higher |
| `cash_kpi.kpi` | 75.0 | 5.0 | higher |
| `cash_kpi.cash_accuracy` | 80.0 | 5.0 | higher |
| `cash_kpi.match_rate` | 0.90 | 0.05 | higher |

## Run individually

```bash
pytest tests/regression -v
```

Current state: **all tests SKIP** because the pipeline writes `reports/<model>/evaluation_metrics.csv` (subfolder, CSV) while this test looks for `reports/*metrics*.json` (root, JSON). Two ways to fix:
1. Extend each model's `evaluate.py` to also dump a JSON alongside the CSV — cleanest, aligns with monitoring layer.
2. Extend `test_metric_baselines.py` to glob recursively and parse CSV — quicker but diverges from other consumers.

Either way, the `baselines.yml` contract is ready.

## Role in orchestration pipeline

Runs **after** a production training run. CI flow:

1. Training run → writes metrics JSON.
2. `pytest tests/regression` reads latest JSON → compares to `baselines.yml`.
3. If worse than `baseline − tolerance` (or `+` for higher-is-better) → CI fails.
4. If genuinely better → operator updates `baselines.yml` + commits.

## Related

- KPI config: `kpi:` block in [config.yml](../../config.yml).
- Source of `cash_kpi`: [monitoring/cash_accuracy.py](../../monitoring/cash_accuracy.py) + [reconciliation/reconcile.py](../../reconciliation/reconcile.py).
- Per-model metrics are produced by the respective `evaluate.py` files under [steps/](../../steps/).
