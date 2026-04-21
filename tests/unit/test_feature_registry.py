import pandas as pd
import pytest

from feature_store.registry import FeatureRegistry
from feature_store.versioning import make_version


def test_unknown_feature_set_rejected(tmp_db):
    with pytest.raises(ValueError, match="Unknown feature set"):
        FeatureRegistry("not_a_real_set")


def test_write_then_read_roundtrip(tmp_db):
    reg = FeatureRegistry("customer_features")
    df = pd.DataFrame([
        {"customer_id": "C1", "avg_days_to_pay": 12.5, "risk_score": 0.2},
        {"customer_id": "C2", "avg_days_to_pay": 30.0, "risk_score": 0.8},
    ])
    v = reg.write(df, entity_col="customer_id", version="test_v1")
    out = reg.read(version=v)
    assert sorted(out["customer_id"]) == ["C1", "C2"]


def test_read_filters_by_entity(tmp_db):
    reg = FeatureRegistry("vendor_features")
    df = pd.DataFrame([
        {"vendor_id": "V1", "avg_delay": 5},
        {"vendor_id": "V2", "avg_delay": 10},
    ])
    reg.write(df, entity_col="vendor_id", version="test_v1")
    out = reg.read(version="test_v1", entity_ids=["V2"])
    assert list(out["vendor_id"]) == ["V2"]


def test_version_is_deterministic():
    v1 = make_version("2026-04-15", "abc")
    v2 = make_version("2026-04-15", "abc")
    v3 = make_version("2026-04-15", "xyz")
    assert v1 == v2
    assert v1 != v3
