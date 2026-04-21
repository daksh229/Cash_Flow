"""
RE Weight Tuner
===============
Nikunj (Q11): "weights will be built from scratch; no prior analysis."

Approach
--------
Start from the config defaults, then nudge them towards whichever
scoring component best explains realised impact. We use a simple
non-negative least-squares fit:

    realised_i ≈ Σ w_k * component_i_k

where `component_i_k` is the score the engine assigned to dimension k
(cash_improvement, risk_reduction, target_alignment, feasibility) for
recommendation i. `w_k` is constrained ≥ 0 and normalised to sum to 1.

We don't over-fit: if there are fewer than `min_samples` accepted
recommendations with realised impact, we keep the existing weights
and log a skip. This avoids wild swings in the first few weeks.

The tuner writes the proposed weights to
  reports/re_weights/<tenant>.json
and tags the `config_hash` so the operator can review before
promoting them into config/recommendation_engine.yml.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from steps.recommendation_engine.feedback_store import load_training_frame

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OUT_DIR = PROJECT_ROOT / "reports" / "re_weights"

COMPONENTS = ("cash_improvement", "risk_reduction", "target_alignment", "feasibility")


def _extract_components(row: Dict) -> Optional[List[float]]:
    payload = row.get("payload") or {}
    comps = payload.get("score_components") or {}
    if not all(c in comps for c in COMPONENTS):
        return None
    return [float(comps[c]) for c in COMPONENTS]


def propose(current_weights: Dict[str, float],
            min_samples: int = 20,
            tenant_id: Optional[str] = None) -> Dict:
    frame = load_training_frame(tenant_id=tenant_id)
    usable = [(row, _extract_components(row)) for row in frame]
    usable = [(r, c) for r, c in usable if c is not None and r["realised"] is not None]

    if len(usable) < min_samples:
        logger.info(
            "weight_tuner: %d samples < min_samples=%d; keeping current weights",
            len(usable), min_samples,
        )
        return {
            "status": "skipped",
            "reason": f"insufficient_data ({len(usable)}/{min_samples})",
            "weights": current_weights,
        }

    X = np.array([c for _, c in usable])
    y = np.array([float(r["realised"]) for r, _ in usable])

    # NNLS-style fit via lstsq + clamp-to-nonneg; good enough for a
    # small advisory signal without adding scipy as a dep.
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    coef = np.clip(coef, 0.0, None)
    total = coef.sum()
    if total <= 0:
        logger.warning("weight_tuner: degenerate fit (sum=0); keeping current")
        return {
            "status": "degenerate",
            "weights": current_weights,
        }
    proposed = dict(zip(COMPONENTS, (coef / total).tolist()))

    out = {
        "status": "proposed",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "tenant_id": tenant_id,
        "sample_size": len(usable),
        "current_weights": current_weights,
        "proposed_weights": {k: round(v, 3) for k, v in proposed.items()},
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUT_DIR / f"{tenant_id or 'default'}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    logger.info("weight_tuner proposal -> %s", path)
    return out


def main():
    import argparse
    import yaml
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--min-samples", type=int, default=20)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    with open(PROJECT_ROOT / "config" / "recommendation_engine.yml") as f:
        cfg = yaml.safe_load(f)
    current = cfg.get("scoring_weights", {})
    print(json.dumps(propose(current, args.min_samples, args.tenant), indent=2))


if __name__ == "__main__":
    main()
