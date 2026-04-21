"""
Role-Based Access Control
=========================
Declares the app's roles and a FastAPI-friendly dependency that enforces
them. Keep roles coarse - fine-grained permissions are an anti-pattern
at this stage and tend to drift.

Role model (matches SSD):
  - viewer    : read forecasts and recommendations
  - analyst   : trigger re-runs, accept/reject recommendations
  - admin     : everything + config changes + user management
"""

from typing import Iterable

from security.auth import verify_token, AuthError


class Role:
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


ROLE_HIERARCHY = {
    Role.ADMIN:   {Role.ADMIN, Role.ANALYST, Role.VIEWER},
    Role.ANALYST: {Role.ANALYST, Role.VIEWER},
    Role.VIEWER:  {Role.VIEWER},
}


def _has_role(granted: Iterable[str], required: str) -> bool:
    for r in granted:
        if required in ROLE_HIERARCHY.get(r, {r}):
            return True
    return False


def require_role(required: str):
    """
    FastAPI dependency factory.

        from fastapi import Depends
        @app.post("/runs", dependencies=[Depends(require_role(Role.ANALYST))])
    """
    from fastapi import Header, HTTPException, status

    def _dep(authorization: str = Header(default="")):
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = verify_token(token)
        except AuthError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
        if not _has_role(claims.get("roles", []), required):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {required}")
        return claims
    return _dep
