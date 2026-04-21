"""
Integration test: running a DAG writes a RunAudit row and flips its
status based on task outcomes.
"""

from db.connection import get_session
from db.models import RunAudit
from orchestrator.dag import PipelineDAG


def test_successful_run_marks_audit_success(tmp_db):
    dag = PipelineDAG(pipeline_name="t_ok")
    dag.add("a", lambda: 1)
    dag.add("b", lambda: 2, depends_on=["a"])
    dag.run()
    with get_session() as s:
        row = s.query(RunAudit).filter_by(pipeline="t_ok").one()
    assert row.status == "success"
    assert row.finished_at is not None


def test_failed_run_marks_audit_failed_with_error(tmp_db):
    dag = PipelineDAG(pipeline_name="t_fail")
    dag.add("a", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    dag.add("b", lambda: 2, depends_on=["a"])
    dag.run()
    with get_session() as s:
        row = s.query(RunAudit).filter_by(pipeline="t_fail").one()
    assert row.status == "failed"
    assert "a" in (row.error or "")
