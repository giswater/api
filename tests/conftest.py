"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

# Force test-specific globals BEFORE app.main is imported so the lifespan
# loads tenants from the fixtures directory.
os.environ.setdefault("BASE_DOMAIN", "bgeo360.com")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")
os.environ.setdefault("LOG_DB_ENABLED", "false")
os.environ.setdefault("GISWATER_DB_VERSION_CHECK", "false")


# Render the 'test' tenant from env vars into a tmp dir so DB_HOST/DB_PORT/etc.
# can be overridden at runtime (the tenant loader reads .env files with
# dotenv_values() and does NOT consult os.environ, so a static fixture file
# would pin the connection params). Defaults match the GH Actions workflow.
def _materialize_tenants_dir() -> str:
    if os.environ.get("TENANTS_DIR"):
        return os.environ["TENANTS_DIR"]
    tmp = Path(tempfile.mkdtemp(prefix="giswater-test-tenants-"))
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "gw_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    # Explicit URL: tenant loader ignores os.environ; sslmode=disable avoids
    # flaky TLS handshakes against Docker/Podman-published Postgres.
    db_url = (
        f"postgresql://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
        f"@{db_host}:{db_port}/{quote(db_name, safe='')}"
        "?application_name=giswater-api&sslmode=disable"
    )
    # DB_SCHEMA is intentionally NOT written here; tests pass it as the
    # `?schema=` query param via the `default_params` fixture.
    (tmp / "test.env").write_text(
        "API_BASIC=true\nAPI_PROFILE=true\nAPI_FLOW=true\nAPI_MINCUT=true\n"
        "API_WATER_BALANCE=true\nAPI_MAPZONES=true\nAPI_ROUTING=true\n"
        "API_CRM=true\nAPI_EPA=true\nAPI_FEATURES=true\n"
        f"DB_HOST={db_host}\nDB_PORT={db_port}\nDB_NAME={db_name}\n"
        f"DB_USER={db_user}\nDB_PASSWORD={db_password}\nDB_SCHEMA=public\n"
        f'DATABASE_URL="{db_url}"\n'
        "DB_POOL_MIN_SIZE=1\nDB_POOL_MAX_SIZE=5\nDB_POOL_TIMEOUT=10\n"
        "DB_POOL_MAX_WAITING=0\nDB_POOL_MAX_IDLE=60\nDB_CONNECT_TIMEOUT=5\n"
        "AUTH_MODE=none\n"
    )
    return str(tmp)


os.environ["TENANTS_DIR"] = _materialize_tenants_dir()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def default_headers() -> dict[str, str]:
    return {"X-Device": "5", "X-Lang": "en_US"}


@pytest.fixture
def default_params() -> dict[str, str]:
    return {"schema": os.getenv("DB_SCHEMA", "public")}


@pytest.fixture
def client(default_headers: dict[str, str]):
    with TestClient(app, base_url="http://test.bgeo360.com", headers=default_headers) as c:
        yield c
