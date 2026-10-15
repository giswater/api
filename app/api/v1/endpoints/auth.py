"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import logging
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import _get_tenant
from app.utils.rate_limit import create_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

_token_rate_limiter = create_rate_limiter(max_requests=10, window_seconds=60, scope="auth_token")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None


class OAuth2ErrorResponse(BaseModel):
    error: str
    error_description: str | None = None


def _oauth_error(status_code: int, error: str, description: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "error_description": description})


def _build_keycloak_form(  # noqa: C901
    *,
    grant_type: str,
    client_id: str | None,
    client_secret: str | None,
    username: str | None,
    password: str | None,
    code: str | None,
    redirect_uri: str | None,
    code_verifier: str | None,
    refresh_token: str | None,
    scope: str | None,
) -> dict[str, str] | JSONResponse:
    if not client_id:
        return _oauth_error(500, "server_error", "Keycloak client not configured")

    form: dict[str, str] = {"grant_type": grant_type, "client_id": client_id}
    if client_secret:
        form["client_secret"] = client_secret
    if scope:
        form["scope"] = scope

    if grant_type == "password":
        if not username or not password:
            return _oauth_error(400, "invalid_request", "username and password are required for password grant")
        form["username"] = username
        form["password"] = password
    elif grant_type == "authorization_code":
        if not code or not redirect_uri:
            return _oauth_error(
                400,
                "invalid_request",
                "code and redirect_uri are required for authorization_code grant",
            )
        form["code"] = code
        form["redirect_uri"] = redirect_uri
        if code_verifier:
            form["code_verifier"] = code_verifier
    elif grant_type == "refresh_token":
        if not refresh_token:
            return _oauth_error(400, "invalid_request", "refresh_token is required for refresh_token grant")
        form["refresh_token"] = refresh_token
    else:
        return _oauth_error(400, "invalid_request", f"Unsupported grant_type '{grant_type}'")

    return form


@router.post(
    "/token",
    summary="Exchange credentials for a Keycloak access token",
    response_model=None,
    responses={
        200: {"model": TokenResponse},
        400: {"model": OAuth2ErrorResponse},
        502: {"model": OAuth2ErrorResponse},
    },
    dependencies=[Depends(_token_rate_limiter)],
)
async def token(
    request: Request,
    grant_type: Annotated[Literal["password", "authorization_code", "refresh_token"], Form()] = "password",
    username: Annotated[str | None, Form()] = None,
    password: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    scope: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    tenant = _get_tenant(request)
    if tenant.settings.auth_mode != "keycloak":
        raise HTTPException(status_code=404, detail="Feature disabled")

    settings = tenant.settings
    form_or_error = _build_keycloak_form(
        grant_type=grant_type,
        client_id=settings.keycloak_client_id,
        client_secret=settings.keycloak_client_secret,
        username=username,
        password=password,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        refresh_token=refresh_token,
        scope=scope,
    )
    if isinstance(form_or_error, JSONResponse):
        return form_or_error

    token_url = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(token_url, data=form_or_error)
    except httpx.RequestError:
        logger.exception("Keycloak token endpoint unreachable for tenant '%s'", tenant.id)
        return _oauth_error(502, "server_error", "Keycloak unreachable")

    try:
        content = resp.json()
    except ValueError:
        content = {"error": "server_error", "error_description": "Invalid response from Keycloak"}

    return JSONResponse(status_code=resp.status_code, content=content)
