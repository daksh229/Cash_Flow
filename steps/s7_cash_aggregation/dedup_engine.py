"""
S7 - Deduplication Engine
=========================
Same cash event can arrive from multiple modules (e.g. S4 pipeline deal
converts into an S1 invoice). Without dedup, S7 double-counts.

Strategy:
  1. Bucket events by (entity_id, amount_rounded, date_window).
  2. Within a bucket, keep the row with the highest trust_score.
  3. Drop the others, but record their event_ids in `duplicates_of`
     so the audit layer can explain the decision later.

date_window defaults to 5 days to tolerate scheduling slippage between
predicted and actual payment dates.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _bucket_key(row, amount_round=-2, date_window_days=5):
    d = pd.to_datetime(row["event_date"])
    bucket_date = d.normalize().to_period(f"{date_window_days}D").start_time
    return (
        str(row["entity_id"]),
        round(float(row["amount"]), amount_round) if amount_round is not None
        else float(row["amount"]),
        bucket_date,
    )


def deduplicate(events: pd.DataFrame, date_window_days=5, amount_round=-2) -> pd.DataFrame:
    if events.empty:
        events = events.copy()
        events["duplicates_of"] = []
        return events

    if "trust_score" not in events.columns:
        raise ValueError("deduplicate expects trust_score column - run trust_scoring first")

    df = events.copy()
    df["_bucket"] = df.apply(
        lambda r: _bucket_key(r, amount_round, date_window_days), axis=1
    )

    kept, dropped = [], []
    for _, group in df.groupby("_bucket", sort=False):
        if len(group) == 1:
            row = group.iloc[0].to_dict()
            row["duplicates_of"] = []
            kept.append(row)
            continue
        group = group.sort_values("trust_score", ascending=False)
        winner = group.iloc[0].to_dict()
        losers = group.iloc[1:]
        winner["duplicates_of"] = losers["event_id"].tolist()
        dropped.extend(losers["event_id"].tolist())
        kept.append(winner)

    out = pd.DataFrame(kept).drop(columns=["_bucket"], errors="ignore")
    logger.info("dedup kept=%d dropped=%d window=%dd",
                len(out), len(dropped), date_window_days)
    return out
