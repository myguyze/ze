from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


async def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    expected: str = request.app.state.settings.ze_api_key
    token = credentials.credentials if credentials else ""
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
