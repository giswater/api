"""Replace legacy gwapi role names with capability ids.

Revision ID: 0003_gwapi_capability_roles
Revises: 0002_gwapi_jobs
Create Date: 2026-10-23

``0001`` seeded ``gwapi.roles`` with ``role_basic``, ``role_edit``, ``role_om``,
``role_epa`` and ``role_master``. Those names are unused. This revision drops
them (and any ``gwapi.user_roles`` rows that point at them) and inserts the
capability ids used by Keycloak and basic-auth: ``basic``, ``om``, ``edit``,
``epa``, ``plan``, ``admin``, ``system``.
"""

from alembic import op

revision = "0003_gwapi_capability_roles"
down_revision = "0002_gwapi_jobs"
branch_labels = None
depends_on = None

_LEGACY_ROLES = ("role_basic", "role_edit", "role_om", "role_epa", "role_master")
_CAPABILITY_ROLES = (
    ("basic", "Basic capability"),
    ("om", "Operations capability"),
    ("edit", "Edit capability"),
    ("epa", "EPA capability"),
    ("plan", "Plan capability"),
    ("admin", "Admin capability"),
    ("system", "System capability"),
)


def _names(names: tuple[str, ...]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def upgrade() -> None:
    legacy = _names(_LEGACY_ROLES)
    op.execute(f"DELETE FROM gwapi.user_roles WHERE role_name IN ({legacy})")
    op.execute(f"DELETE FROM gwapi.roles WHERE name IN ({legacy})")
    op.execute(
        """
        INSERT INTO gwapi.roles (name, description) VALUES
            ('basic', 'Basic capability'),
            ('om', 'Operations capability'),
            ('edit', 'Edit capability'),
            ('epa', 'EPA capability'),
            ('plan', 'Plan capability'),
            ('admin', 'Admin capability'),
            ('system', 'System capability')
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    current = _names(tuple(name for name, _description in _CAPABILITY_ROLES))
    op.execute(f"DELETE FROM gwapi.user_roles WHERE role_name IN ({current})")
    op.execute(f"DELETE FROM gwapi.roles WHERE name IN ({current})")
    op.execute(
        """
        INSERT INTO gwapi.roles (name, description) VALUES
            ('role_basic', 'Basic read access'),
            ('role_edit', 'Edit access'),
            ('role_om', 'Operations and maintenance'),
            ('role_epa', 'EPA / scenario access'),
            ('role_master', 'Master access')
        ON CONFLICT (name) DO NOTHING
        """
    )
