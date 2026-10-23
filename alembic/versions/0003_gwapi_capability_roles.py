"""Seed gwapi.roles with the Giswater capability role names.

Revision ID: 0003_gwapi_capability_roles
Revises: 0002_gwapi_jobs
Create Date: 2026-10-23

Basic-auth ``gwapi.user_roles.role_name`` references ``gwapi.roles``. The
capability defaults (``basic``, ``om``, ``edit``, ``epa``, ``plan``, ``admin``,
``system``) must exist there so a tenant can assign them. Older catalog rows
(``role_basic``, ``role_master``, …) stay.
"""

from alembic import op

revision = "0003_gwapi_capability_roles"
down_revision = "0002_gwapi_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.execute(
        """
        DELETE FROM gwapi.user_roles
        WHERE role_name IN ('basic', 'om', 'edit', 'epa', 'plan', 'admin', 'system')
        """
    )
    op.execute(
        """
        DELETE FROM gwapi.roles
        WHERE name IN ('basic', 'om', 'edit', 'epa', 'plan', 'admin', 'system')
        """
    )
