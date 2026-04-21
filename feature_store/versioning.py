"""
Feature Versioning
==================
Deterministic version string for a feature snapshot. Uses the master
config's reference_date plus a short hash of the source-data fingerprint.

A version string pins a feature set to the raw data it was built from,
so downstream models can be replayed against the exact same features.
"""

import hashlib
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def make_version(reference_date, fingerprint=None):
    base = str(reference_date)
    if fingerprint:
        h = hashlib.sha256(fingerprint.encode()).hexdigest()[:8]
        return f"{base}_{h}"
    return base


def current_version():
    with open(PROJECT_ROOT / "config.yml", "r") as f:
        cfg = yaml.safe_load(f)
    ref = cfg.get("global", {}).get("reference_date")
    if not ref:
        ref = datetime.utcnow().date().isoformat()
    return make_version(ref)
