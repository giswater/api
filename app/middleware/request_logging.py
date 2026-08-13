import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from starlette.responses import Response

from ..tenancy import state
from ..core.config import global_settings
from ..core.constants import ADMIN_PREFIX, GLOBAL_HEALTH_PATH, STATIC_PREFIX, TENANT_API_PREFIXES
from ..db.context import DB_IDENTITY_CTX, REQUEST_ID_CTX
from ..db.log_store import insert_api_log

# Endpoints where request/response bodies are not worth storing (e.g. they
# return log data itself, static content, or trivial health payloads).
# Metadata (method, path, status, duration, user, IP) is still logged.
_SKIP_BODY_PREFIXES = ("/logs", "/health", "/favicon.ico", "/docs", "/openapi.json")
_SKIP_BODY_CONTENT_TYPES = ("multipart/form-data", "application/octet-stream")
_CAPTURE_FULL_BODY_STATUS_CODES = {400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504}
_REDACTED = "***REDACTED***"
_SENSITIVE_FIELD_MARKERS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "keycloak",
    "db_password",
    "client_secret",
)

# When LOG_HTTP_BODY_CAPTURE is enabled but LOG_DB_MAX_BODY_BYTES=0, apply this cap (bytes).
_DEFAULT_SAFE_BODY_CAP = 2048


def _effective_body_byte_cap() -> int:
    """Upper bound for stored body bytes when capture is enabled; avoids unlimited retention."""
    cap = global_settings.log_db_max_body_bytes
    if cap <= 0:
        return _DEFAULT_SAFE_BODY_CAP
    return cap


LOG_HEADER_ALLOWLIST = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "content-length",
    "content-type",
    "etag",
    "user-agent",
    "x-device",
    "x-lang",
    "x-forwarded-for",
    "x-real-ip",
    "x-request-id",
}


def _filter_headers(headers: dict) -> dict:
    return {key: value for key, value in headers.items() if key in LOG_HEADER_ALLOWLIST}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_FIELD_MARKERS)


def _redact_object(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = _REDACTED
            else:
                redacted[key] = _redact_object(item)
        return redacted
    if isinstance(value, list):
        return [_redact_object(item) for item in value]
    return value


def _sanitize_body_text(body_bytes: bytes | None) -> str | None:
    if not body_bytes:
        return None
    body_text = body_bytes.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body_text)
    except (TypeError, ValueError):
        return _truncate_body(body_text.encode("utf-8", errors="replace")).decode("utf-8", errors="replace")
    redacted = _redact_object(parsed)
    sanitized = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
    return _truncate_body(sanitized.encode("utf-8", errors="replace")).decode("utf-8", errors="replace")


def _should_capture_body_for_status(status_code: int) -> bool:
    return status_code in _CAPTURE_FULL_BODY_STATUS_CODES


def _should_skip_content_type(request: Request) -> bool:
    content_type = (request.headers.get("content-type") or "").lower()
    return any(marker in content_type for marker in _SKIP_BODY_CONTENT_TYPES)


async def _resolve_api_logger(request: Request):
    """Return the appropriate file logger: tenant logger when present, else global."""
    tenant = getattr(request.state, "tenant", None)
    if tenant is not None:
        await tenant.ensure_logger_fresh()
        return tenant.api_logger
    return state.global_logger


def _tenant_api_rest(path: str) -> str | None:
    """Return the path under a tenant API prefix, or None if not a tenant API path."""
    for prefix in TENANT_API_PREFIXES:
        if not _path_starts(path, prefix):
            continue
        rest = path[len(prefix) :] if path.startswith(prefix) else path
        if not rest.startswith("/"):
            rest = "/" + rest
        return rest
    return None


def _is_global_path(path: str) -> bool:
    """Paths that must not write tenant-scoped rows to the API log DB."""
    if path == "/" or _path_starts(path, GLOBAL_HEALTH_PATH) or _path_starts(path, STATIC_PREFIX):
        return True
    if _path_starts(path, ADMIN_PREFIX):
        return True
    rest = _tenant_api_rest(path)
    if rest is None:
        return False
    if rest.startswith("/openapi.json") or rest.startswith("/docs") or rest.startswith("/redoc"):
        return True
    if "/openapi.json" in path:
        return True
    if rest.startswith("/logs") or _path_starts(rest, "/health"):
        return True
    return False


def _path_starts(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _get_user_name(request: Request) -> str | None:
    user_name = getattr(request.state, "user", None)
    if user_name:
        return user_name
    return request.headers.get("x-user") or request.headers.get("x-auth-user")


def _get_body_size(request: Request) -> int | None:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        return int(content_length)
    return None


def _coerce_body_bytes(body) -> bytes | None:
    if body is None:
        return None
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return str(body).encode()


def _truncate_body(body_bytes: bytes) -> bytes:
    cap = _effective_body_byte_cap()
    if len(body_bytes) > cap:
        return body_bytes[:cap] + b"...[truncated]"
    return body_bytes


def _body_to_text(body_bytes: bytes | None) -> str | None:
    if not body_bytes:
        return None
    return _truncate_body(body_bytes).decode("utf-8", errors="replace")


def _get_response_size(response_body: bytes | None) -> int | None:
    if not response_body:
        return None
    try:
        return len(response_body)
    except TypeError:
        return None


async def _capture_response_body(response):
    if response is None:
        return None, None
    body = getattr(response, "body", None)
    if body is not None:
        return response, _coerce_body_bytes(body)
    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        return response, None

    chunks: list[bytes] = []
    async for chunk in body_iterator:
        if isinstance(chunk, (bytes, bytearray)):
            chunks.append(bytes(chunk))
        else:
            chunks.append(str(chunk).encode())
    body_bytes = b"".join(chunks)
    headers = dict(response.headers)
    headers.pop("content-length", None)
    new_response = Response(
        content=body_bytes,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
    )
    return new_response, body_bytes


def _build_log_record(
    request: Request,
    response,
    response_body: bytes | None,
    request_id: uuid.UUID,
    status_code: int,
    duration_ms: int,
    error: Exception | None,
    request_body: bytes,
    *,
    capture_bodies: bool,
    skip_body_path: bool = False,
):
    request_headers = _filter_headers({key.lower(): value for key, value in request.headers.items()})
    response_headers = None
    response_body_text = None
    request_body_text = None
    if response is not None:
        response_headers = _filter_headers({key.lower(): value for key, value in response.headers.items()})
        if capture_bodies and not skip_body_path:
            response_body_text = _sanitize_body_text(response_body)
    if capture_bodies and not skip_body_path:
        request_body_text = _sanitize_body_text(request_body)
    query_params = _redact_object(dict(request.query_params))

    return {
        "ts": datetime.now(timezone.utc),
        "method": request.method,
        "endpoint": request.url.path,
        "status": status_code,
        "duration_ms": duration_ms,
        "user_name": _get_user_name(request),
        "request_id": request_id,
        "client_ip": _get_client_ip(request),
        "query_params": query_params,
        "body_size": _get_body_size(request),
        "response_size": _get_response_size(response_body),
        "request_headers": request_headers,
        "request_body": request_body_text,
        "response_headers": response_headers,
        "response_body": response_body_text,
        "error": str(error) if error else None,
    }


def _should_log_db() -> bool:
    if not global_settings.log_db_enabled or global_settings.log_db_sample_rate <= 0.0:
        return False
    return global_settings.log_db_sample_rate >= 1.0 or random.random() <= global_settings.log_db_sample_rate


async def request_logging_middleware(request: Request, call_next):
    start = time.monotonic()
    request_id = uuid.uuid4()
    request.state.request_id = request_id
    token = REQUEST_ID_CTX.set(request_id)
    DB_IDENTITY_CTX.set(None)
    request_body = await request.body()

    response = None
    response_body = None
    status_code = 500
    error = None
    try:
        response = await call_next(request)
        status_code = response.status_code
    except HTTPException as exc:
        status_code = exc.status_code
        error = exc
        raise
    except Exception as exc:  # noqa: BLE001
        status_code = 500
        error = exc
        raise
    finally:
        REQUEST_ID_CTX.reset(token)
        DB_IDENTITY_CTX.set(None)
        duration_ms = int((time.monotonic() - start) * 1000)
        path = request.url.path
        skip_body_path = any(prefix in path for prefix in _SKIP_BODY_PREFIXES)
        capture_bodies = (
            global_settings.log_http_body_capture
            and not skip_body_path
            and not _should_skip_content_type(request)
            and _should_capture_body_for_status(status_code)
        )
        if capture_bodies:
            response, response_body = await _capture_response_body(response)
        else:
            response_body = None
        log_record = _build_log_record(
            request=request,
            response=response,
            response_body=response_body,
            request_id=request_id,
            status_code=status_code,
            duration_ms=duration_ms,
            error=error,
            request_body=request_body,
            capture_bodies=capture_bodies,
            skip_body_path=skip_body_path,
        )

        api_logger = await _resolve_api_logger(request)
        if api_logger is not None:
            api_logger.info(json.dumps(log_record, default=str))

        # DB API log: only for tenant-scoped requests. Global endpoints
        # (admin, health, static) skip DB logging.
        tenant = getattr(request.state, "tenant", None)
        if tenant is not None and not _is_global_path(path) and _should_log_db():
            asyncio.create_task(insert_api_log(tenant.db_manager, log_record))

        if response is not None:
            response.headers["X-Request-ID"] = str(request_id)

    return response
