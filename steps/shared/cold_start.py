"""
Cold-Start & Context-Aware Prior
================================
Nikunj called this the "core architectural unlock" (Q&A row 8):

  - new customers have zero history -> ML can't learn per-entity
  - existing customers still vary by season, invoice value, dispute
    status, invoice count, etc.

Design
------
A three-level hierarchical prior for `days_to_pay` (and any similar
target). When a prediction is requested for (customer, invoice), we
blend three sources:

  level 1 : customer-level history (if n_invoices >= min_customer_n)
  level 2 : segment-level history  (risk_band + amount_bucket + season)
  level 3 : global-level history   (everyone)

Weights use empirical-Bayes shrinkage:
    w_customer = n_customer / (n_customer + tau)
    remainder goes to segment/global proportionally.

This is NOT a model replacement. It produces a *prior* that:
  a) serves cold-start customers directly,
  b) becomes a feature for S1/S2 ML models so they can learn to
     deviate from the prior with confidence.

Usage
-----
    prior = GlobalPrior.fit(history_df, target_col="days_to_pay",
                            entity_col="customer_id")
    prior.save()                                  # persists to models/
    predicted = prior.predict(context_df)         # returns Series
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PATH = PROJECT_ROOT / "models" / "cold_start_prior.pkl"


def _infer_season(dt) -> str:
    if pd.isna(dt):
        return "unknown"
    m = pd.Timestamp(dt).month
    return {12: "Q4", 1: "Q4", 2: "Q4",
            3: "Q1", 4: "Q1", 5: "Q1",
            6: "Q2", 7: "Q2", 8: "Q2",
            9: "Q3", 10: "Q3", 11: "Q3"}[m]


def _infer_amount_bucket(amount: float) -> str:
    if pd.isna(amount):
        return "UNK"
    if amount < 10_000:
        return "S"
    if amount < 100_000:
        return "M"
    return "L"


@dataclass
class GlobalPrior:
    target_col: str = "days_to_pay"
    entity_col: str = "customer_id"
    tau: float = 5.0                              # shrinkage strength
    min_customer_n: int = 3

    global_stats: Dict = field(default_factory=dict)
    segment_stats: Dict = field(default_factory=dict)   # keyed by (risk, bucket, season)
    customer_stats: Dict = field(default_factory=dict)  # keyed by entity_id

    @staticmethod
    def _aggregate(df: pd.DataFrame, target_col: str):
        if df.empty:
            return {"mean": None, "std": None, "n": 0}
        return {
            "mean": float(df[target_col].mean()),
            "std":  float(df[target_col].std(ddof=0) or 0.0),
            "n":    int(len(df)),
        }

    @classmethod
    def fit(cls, df: pd.DataFrame, target_col="days_to_pay",
            entity_col="customer_id",
            date_col="invoice_date", amount_col="invoice_amount",
            risk_col="risk_segment", tau=5.0) -> "GlobalPrior":

        required = {target_col, entity_col}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"GlobalPrior.fit missing columns: {missing}")

        work = df.copy()
        work = work.dropna(subset=[target_col])

        if date_col in work.columns:
            work["_season"] = work[date_col].apply(_infer_season)
        else:
            work["_season"] = "unknown"
        if amount_col in work.columns:
            work["_bucket"] = work[amount_col].apply(_infer_amount_bucket)
        else:
            work["_bucket"] = "UNK"
        if risk_col not in work.columns:
            work[risk_col] = "MEDIUM"

        inst = cls(target_col=target_col, entity_col=entity_col, tau=tau)
        inst.global_stats = cls._aggregate(work, target_col)

        for key, grp in work.groupby([risk_col, "_bucket", "_season"]):
            inst.segment_stats["|".join(map(str, key))] = cls._aggregate(grp, target_col)
        for ent, grp in work.groupby(entity_col):
            inst.customer_stats[str(ent)] = cls._aggregate(grp, target_col)

        logger.info(
            "GlobalPrior fit: global_n=%s segments=%d customers=%d tau=%s",
            inst.global_stats["n"], len(inst.segment_stats),
            len(inst.customer_stats), tau,
        )
        return inst

    def _segment_key(self, row) -> str:
        return "|".join([
            str(row.get("risk_segment", "MEDIUM")),
            _infer_amount_bucket(row.get("invoice_amount", np.nan)),
            _infer_season(row.get("invoice_date", pd.NaT)),
        ])

    def predict_one(self, row) -> Dict:
        g = self.global_stats or {"mean": None, "n": 0}
        g_mean = g["mean"]
        if g_mean is None:
            return {"predicted": None, "source": "unknown",
                    "w_customer": 0, "w_segment": 0, "w_global": 0}

        cust = self.customer_stats.get(str(row.get(self.entity_col, "")),
                                       {"mean": None, "n": 0})
        seg = self.segment_stats.get(self._segment_key(row),
                                     {"mean": None, "n": 0})

        n_c = cust["n"] if cust["mean"] is not None else 0
        n_s = seg["n"] if seg["mean"] is not None else 0
        w_c = n_c / (n_c + self.tau) if n_c >= self.min_customer_n else 0.0
        remaining = 1 - w_c
        w_s = remaining * (n_s / (n_s + self.tau)) if n_s else 0.0
        w_g = remaining - w_s

        val = (
            w_c * (cust["mean"] or 0.0) +
            w_s * (seg["mean"] or 0.0) +
            w_g * g_mean
        )
        source = "customer" if w_c >= 0.5 else ("segment" if w_s >= 0.3 else "global")
        return {
            "predicted": float(val),
            "source": source,
            "w_customer": round(w_c, 3),
            "w_segment": round(w_s, 3),
            "w_global": round(w_g, 3),
        }

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.apply(lambda r: self.predict_one(r), axis=1, result_type="expand")
        return out

    def save(self, path=None):
        path = Path(path or _DEFAULT_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("GlobalPrior saved to %s", path)
        return path

    @classmethod
    def load(cls, path=None) -> Optional["GlobalPrior"]:
        path = Path(path or _DEFAULT_PATH)
        if not path.exists():
            return None
        return joblib.load(path)

    def to_json(self) -> str:
        return json.dumps({
            "target_col": self.target_col,
            "entity_col": self.entity_col,
            "tau": self.tau,
            "global": self.global_stats,
            "segments": len(self.segment_stats),
            "customers": len(self.customer_stats),
        }, default=str)
