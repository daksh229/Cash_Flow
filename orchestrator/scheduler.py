"""
Scheduler
=========
Thin wrapper around PipelineDAG that wires the real model runners from
steps/ into tasks and kicks off a run. Intended as the production
replacement for pipeline/run_all.py.

Trigger sources:
  - CLI         : python -m orchestrator.scheduler
  - Events      : events.listeners calls Scheduler.run_subgraph(...)
  - Cron/API    : to be added in deployment area
"""

import logging
from pathlib import Path

import yaml

from orchestrator.dag import PipelineDAG
from orchestrator.dependencies import MODEL_DEPENDENCIES

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_master_cfg():
    with open(PROJECT_ROOT / "config.yml", "r") as f:
        return yaml.safe_load(f)


def _model_runner(model_key, master_cfg):
    """Return a zero-arg callable that runs one model end-to-end."""
    def _run():
        from main import _load_model_config, _run_model_pipeline
        model_cfg = _load_model_config(model_key)
        return _run_model_pipeline(model_key, master_cfg, model_cfg)
    return _run


def _feature_table_runner(master_cfg):
    def _run():
        from main import _run_feature_table
        return _run_feature_table(master_cfg["global"])
    return _run


class Scheduler:
    @staticmethod
    def build_full_dag():
        master_cfg = _load_master_cfg()
        enabled = set(master_cfg.get("models", []))
        dag = PipelineDAG(pipeline_name="full")

        dag.add("feature_table", _feature_table_runner(master_cfg))
        for model_key, deps in MODEL_DEPENDENCIES.items():
            if model_key == "feature_table" or model_key not in enabled:
                continue
            active_deps = [d for d in deps if d == "feature_table" or d in enabled]
            dag.add(model_key, _model_runner(model_key, master_cfg), depends_on=active_deps)
        return dag

    @staticmethod
    def run_full():
        dag = Scheduler.build_full_dag()
        return dag.run()

    @staticmethod
    def run_subgraph(model_keys):
        """Re-run a subset (+ their downstreams). Used by event listeners."""
        master_cfg = _load_master_cfg()
        dag = PipelineDAG(pipeline_name=f"subgraph:{','.join(model_keys)}")
        requested = set(model_keys)
        closure = set(requested)
        changed = True
        while changed:
            changed = False
            for k, deps in MODEL_DEPENDENCIES.items():
                if k in closure:
                    continue
                if any(d in closure for d in deps):
                    closure.add(k)
                    changed = True

        for k in closure:
            deps = [d for d in MODEL_DEPENDENCIES[k] if d in closure]
            fn = _feature_table_runner(master_cfg) if k == "feature_table" \
                else _model_runner(k, master_cfg)
            dag.add(k, fn, depends_on=deps)
        return dag.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )
    Scheduler.run_full()
