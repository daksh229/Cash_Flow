import pytest

from orchestrator.dag import PipelineDAG


def test_topological_order_respects_dependencies(tmp_db):
    order_log = []
    dag = PipelineDAG(pipeline_name="test")
    dag.add("a", lambda: order_log.append("a"))
    dag.add("b", lambda: order_log.append("b"), depends_on=["a"])
    dag.add("c", lambda: order_log.append("c"), depends_on=["b"])
    dag.run()
    assert order_log == ["a", "b", "c"]


def test_failed_upstream_skips_downstream(tmp_db):
    def boom():
        raise RuntimeError("nope")

    dag = PipelineDAG(pipeline_name="test")
    dag.add("a", boom)
    dag.add("b", lambda: 1, depends_on=["a"])
    result = dag.run()
    assert result["a"].status == "failed"
    assert result["b"].status == "skipped"


def test_cycle_detection(tmp_db):
    dag = PipelineDAG(pipeline_name="test")
    dag.add("a", lambda: 1, depends_on=["b"])
    dag.add("b", lambda: 1, depends_on=["a"])
    with pytest.raises(ValueError, match="Cycle"):
        dag.run()


def test_unknown_dependency_raises(tmp_db):
    dag = PipelineDAG(pipeline_name="test")
    dag.add("a", lambda: 1, depends_on=["missing"])
    with pytest.raises(KeyError):
        dag.run()
