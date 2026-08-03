"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from pathlib import Path

from app.db.migrate import _alembic_ini, build_alembic_config, head_revision


def test_alembic_ini_exists():
    ini = _alembic_ini()
    assert ini.is_file()
    assert (ini.parent / "alembic" / "env.py").is_file()
    assert (ini.parent / "alembic" / "versions" / "0001_gwapi_initial.py").is_file()
    assert (ini.parent / "alembic" / "versions" / "0002_gwapi_jobs.py").is_file()


def test_build_alembic_config_uses_project_ini():
    cfg = build_alembic_config("postgresql://user:pass@localhost/db")
    assert Path(cfg.config_file_name).name == "alembic.ini"
    assert cfg.get_main_option("script_location") == "alembic"


def test_build_alembic_config_escapes_percent_in_database_url():
    cfg = build_alembic_config("postgresql://user:p%40ss@localhost/db")
    assert cfg.get_main_option("sqlalchemy.url") == "postgresql+psycopg://user:p%40ss@localhost/db"


def test_head_revision_is_latest():
    assert head_revision() == "0002_gwapi_jobs"
