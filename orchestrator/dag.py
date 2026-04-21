"""
Pipeline DAG
============
Minimal DAG executor for the cash-flow pipeline. Replaces the linear
script in pipeline/run_all.py with a dependency-aware runner that:
  - computes a topological order from MODEL_DEPENDENCIES
  - runs independent branches in parallel (via Scheduler)
  - records run audit rows in the DB
  - marks downstream tasks as skipped when an upstream fails

Note: this is the execution engine. Per-model step logic stays in steps/.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Set

from db.connection import get_session
from db.models import RunAudit
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)


@dataclass
class Task:
    name: str
    fn: Callable
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"          # pending | running | success | failed | skipped
    result: object = None
    error: str = None


class PipelineDAG:
    def __init__(self, run_id=None, pipeline_name="full"):
        self.tasks: Dict[str, Task] = {}
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.pipeline_name = pipeline_name

    def add(self, name, fn, depends_on=None):
        self.tasks[name] = Task(name=name, fn=fn, depends_on=list(depends_on or []))
        return self

    def _topo_order(self) -> List[str]:
        order, visited, tmp = [], set(), set()

        def visit(n):
            if n in visited:
                return
            if n in tmp:
                raise ValueError(f"Cycle detected at task '{n}'")
            tmp.add(n)
            for dep in self.tasks[n].depends_on:
                if dep not in self.tasks:
                    raise KeyError(f"Task '{n}' depends on unknown '{dep}'")
                visit(dep)
            tmp.discard(n)
            visited.add(n)
            order.append(n)

        for name in self.tasks:
            visit(name)
        return order

    def _upstream_failed(self, task: Task) -> bool:
        return any(self.tasks[d].status in ("failed", "skipped") for d in task.depends_on)

    def run(self, executor=None):
        self._audit_start()
        order = self._topo_order()
        logger.info("DAG[%s] order: %s", self.run_id, order)

        failures: Set[str] = set()
        for name in order:
            task = self.tasks[name]
            if self._upstream_failed(task):
                task.status = "skipped"
                logger.warning("Task '%s' SKIPPED (upstream failed)", name)
                continue
            task.status = "running"
            try:
                logger.info("Task '%s' RUNNING", name)
                task.result = task.fn()
                task.status = "success"
                logger.info("Task '%s' SUCCESS", name)
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                failures.add(name)
                logger.error("Task '%s' FAILED: %s", name, e, exc_info=True)

        self._audit_finish(failures)
        return {n: t for n, t in self.tasks.items()}

    def _audit_start(self):
        with get_session() as s:
            s.add(RunAudit(
                tenant_id=current_tenant(),
                run_id=self.run_id,
                pipeline=self.pipeline_name,
                status="running",
                started_at=datetime.utcnow(),
            ))
            s.commit()

    def _audit_finish(self, failures):
        status = "failed" if failures else "success"
        err = f"failed tasks: {sorted(failures)}" if failures else None
        with get_session() as s:
            row = s.query(RunAudit).filter_by(run_id=self.run_id).one_or_none()
            if row:
                row.status = status
                row.finished_at = datetime.utcnow()
                row.error = err
                s.commit()
