"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from urllib.parse import quote

from app.core.constants import ADMIN_PREFIX

from tests.helpers import assert_ready


def _run_subprocess(script: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: stderr={proc.stderr!r} stdout={proc.stdout!r}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _tenant_env_body(auth_mode: str) -> str:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "gw_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    db_schema = os.getenv("DB_SCHEMA", "public")
    db_url = (
        f"postgresql://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
        f"@{db_host}:{db_port}/{quote(db_name, safe='')}"
        "?application_name=giswater-api&sslmode=disable"
    )
    return (
        "API_BASIC=true\nAPI_PROFILE=true\nAPI_FLOW=true\nAPI_MINCUT=true\n"
        "API_WATER_BALANCE=true\nAPI_MAPZONES=true\nAPI_ROUTING=true\n"
        "API_CRM=true\nAPI_EPA=true\nAPI_FEATURES=true\n"
        f"DB_HOST={db_host}\nDB_PORT={db_port}\nDB_NAME={db_name}\n"
        f"DB_USER={db_user}\nDB_PASSWORD={db_password}\nDB_SCHEMA={db_schema}\n"
        f'DATABASE_URL="{db_url}"\n'
        "DB_POOL_MIN_SIZE=1\nDB_POOL_MAX_SIZE=5\nDB_POOL_TIMEOUT=10\n"
        "DB_CONNECT_TIMEOUT=5\n"
        f"AUTH_MODE={auth_mode}\n"
        f"AUTH_BASIC_BOOTSTRAP_USER={db_user}\n"
        "AUTH_BASIC_BOOTSTRAP_PASSWORD=smokepass99\n"
    )


def _schema_param() -> str:
    return os.getenv("DB_SCHEMA", "public")


def _auth_subprocess_script(auth_mode: str, request_snippet: str) -> str:
    tenants_dir = tempfile.mkdtemp(prefix="giswater-auth-smoke-")
    env_path = os.path.join(tenants_dir, "smoke.env")
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write(_tenant_env_body(auth_mode))

    return textwrap.dedent(
        f"""
        import json, os
        os.environ["SINGLE_TENANT_ID"] = "smoke"
        os.environ["TENANTS_DIR"] = {tenants_dir!r}
        os.environ.setdefault("ADMIN_USER", "admin")
        os.environ.setdefault("ADMIN_PASSWORD", "admin")
        os.environ.setdefault("LOG_DB_ENABLED", "false")
        os.environ.setdefault("GISWATER_DB_VERSION_CHECK", "false")

        from fastapi.testclient import TestClient
        from app.core.constants import TENANT_PREFIX
        from app.main import app

        with TestClient(
            app,
            base_url="http://127.0.0.1",
            headers={{"X-Device": "5", "X-Lang": "en_US"}},
        ) as c:
        {textwrap.indent(request_snippet, "    ")}
        """
    )


def test_basic_auth_missing_credentials_401():
    schema = _schema_param()
    script = _auth_subprocess_script(
        "basic",
        f"""
        r = c.get(f"{{TENANT_PREFIX}}/basic/getlist", params={{"schema": {schema!r}}})
        print(json.dumps({{"status": r.status_code}}))
        """,
    )
    data = _run_subprocess(script)
    assert data["status"] == 401


def test_basic_auth_invalid_credentials_401():
    schema = _schema_param()
    script = _auth_subprocess_script(
        "basic",
        f"""
        r = c.get(
            f"{{TENANT_PREFIX}}/basic/getlist",
            params={{"schema": {schema!r}}},
            auth=("wrong", "credentials"),
        )
        print(json.dumps({{"status": r.status_code}}))
        """,
    )
    data = _run_subprocess(script)
    assert data["status"] == 401


def test_none_mode_allows_anonymous():
    schema = _schema_param()
    script = _auth_subprocess_script(
        "none",
        f"""
        r = c.get(f"{{TENANT_PREFIX}}/basic/getlist", params={{"schema": {schema!r}}})
        print(json.dumps({{"status": r.status_code}}))
        """,
    )
    data = _run_subprocess(script)
    assert data["status"] != 401


def test_basic_auth_valid_credentials(client, default_params):
    """Requires Postgres; bootstrap user is created on tenant load."""
    assert_ready(client)
    schema = _schema_param()
    bootstrap_user = os.getenv("DB_USER", "postgres")

    script = _auth_subprocess_script(
        "basic",
        f"""
        r = c.get(
            f"{{TENANT_PREFIX}}/basic/getlist",
            params={{"schema": {schema!r}, "tableName": "ve_arc"}},
            auth=({bootstrap_user!r}, "smokepass99"),
        )
        print(json.dumps({{"status": r.status_code}}))
        """,
    )
    data = _run_subprocess(script)
    assert data["status"] == 200


def test_admin_users_smoke(client):
    """Admin user CRUD on a basic-auth tenant (requires Postgres)."""
    assert_ready(client)
    admin_headers = {"host": "bgeo360.com"}

    pg_role = os.getenv("DB_USER", "postgres")
    create_payload = {
        "id": "authtest",
        "api": {"basic": True},
        "db": {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "5432"),
            "name": os.getenv("DB_NAME", "gw_db"),
            "user": pg_role,
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "schema": os.getenv("DB_SCHEMA", "public"),
            "pool_min_size": 1,
            "pool_max_size": 5,
            "pool_timeout": 10,
            "connect_timeout": 5,
        },
        "auth": {
            "mode": "basic",
            "bootstrapUser": pg_role,
            "bootstrapPassword": "authtest99!",
        },
    }

    created = client.post(
        f"{ADMIN_PREFIX}/tenants",
        json=create_payload,
        headers=admin_headers,
        auth=("admin", "admin"),
    )
    assert created.status_code == 201, created.text

    try:
        listed = client.get(
            f"{ADMIN_PREFIX}/tenants/authtest/users",
            headers=admin_headers,
            auth=("admin", "admin"),
        )
        assert listed.status_code == 200
        assert isinstance(listed.json(), list)

        dup = client.post(
            f"{ADMIN_PREFIX}/tenants/authtest/users",
            json={
                "username": "extra_user",
                "password": "extrauser1",
                "db_role": pg_role,
                "roles": ["role_basic"],
            },
            headers=admin_headers,
            auth=("admin", "admin"),
        )
        assert dup.status_code == 201

        dup2 = client.post(
            f"{ADMIN_PREFIX}/tenants/authtest/users",
            json={
                "username": "extra_user",
                "password": "extrauser1",
                "db_role": pg_role,
                "roles": ["role_basic"],
            },
            headers=admin_headers,
            auth=("admin", "admin"),
        )
        assert dup2.status_code == 400
        assert "already exists" in dup2.json()["detail"].lower()
    finally:
        client.delete(
            f"{ADMIN_PREFIX}/tenants/authtest",
            headers=admin_headers,
            auth=("admin", "admin"),
        )
