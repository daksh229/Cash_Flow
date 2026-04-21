"""
Health Checks
=============
Two probes for K8s-style orchestrators:
  /health/live   : process is alive
  /health/ready  : process can serve traffic (DB reachable, migrations applied)

The ready check runs a cheap DB query. Keep checks fast - they run every
few seconds and a slow probe will flap.
"""

import logging

logger = logging.getLogger(__name__)


class HealthCheck:
    @staticmethod
    def live() -> dict:
        return {"status": "live"}

    @staticmethod
    def ready() -> dict:
        issues = []
        try:
            from sqlalchemy import text
            from db.connection import get_engine
            with get_engine().connect() as c:
                c.execute(text("SELECT 1"))
        except Exception as e:
            issues.append(f"db:{e.__class__.__name__}")

        return {
            "status": "ready" if not issues else "not_ready",
            "issues": issues,
        }


def register_health_routes(app):
    """Attach /health/live, /health/ready, /metrics to a FastAPI app."""
    from fastapi import Response

    @app.get("/health/live")
    def _live():
        return HealthCheck.live()

    @app.get("/health/ready")
    def _ready():
        result = HealthCheck.ready()
        status_code = 200 if result["status"] == "ready" else 503
        return Response(
            content=str(result), media_type="application/json", status_code=status_code
        )

    @app.get("/metrics")
    def _metrics():
        from monitoring.metrics import metrics as m
        return Response(content=m.export_prometheus(), media_type="text/plain; version=0.0.4")
