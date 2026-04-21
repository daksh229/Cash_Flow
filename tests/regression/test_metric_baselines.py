"""
Regression gate: current metrics must not drift below documented baselines.

The check reads the latest metrics JSON from reports/ and compares each
entry against tests/regression/baselines.yml. Failing this test means
either the baseline should be lifted (real improvement) or the change
is regressing quality and needs investigation.

When reports/ has no metrics file yet (fresh clone), the test skips -
so it won't block early development.
"""

import json
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINES = PROJECT_ROOT / "tests" / "regression" / "baselines.yml"
REPORTS = PROJECT_ROOT / "reports"


def _load_latest_metrics(model_key):
    candidates = sorted(REPORTS.glob(f"{model_key}*metrics*.json"))
    if not candidates:
        return None
    with open(candidates[-1], "r") as f:
        return json.load(f)


def _compare(metric_name, current, spec):
    limit = spec["value"] - spec["tolerance"] if spec["direction"] == "higher_is_better" \
        else spec["value"] + spec["tolerance"]
    ok = current >= limit if spec["direction"] == "higher_is_better" else current <= limit
    return ok, limit


@pytest.mark.parametrize("model_key", [
    "s1_ar_prediction", "s2_ap_prediction", "credit_risk", "s7_cash_aggregation",
])
def test_model_not_below_baseline(model_key):
    with open(BASELINES, "r") as f:
        baselines = yaml.safe_load(f)
    metrics = _load_latest_metrics(model_key)
    if metrics is None:
        pytest.skip(f"no metrics file yet for {model_key}")
    for name, spec in baselines.get(model_key, {}).items():
        if name not in metrics:
            pytest.skip(f"{model_key}.{name} not present in latest metrics")
        ok, limit = _compare(name, metrics[name], spec)
        assert ok, f"{model_key}.{name}={metrics[name]} worse than limit {limit}"
