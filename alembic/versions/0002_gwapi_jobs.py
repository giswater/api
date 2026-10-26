"""gwapi jobs table for background job tracking

Revision ID: 0002_gwapi_jobs
Revises: 0001_gwapi_initial
Create Date: 2026-08-03

Creates ``gwapi.jobs`` (and indexes) used by the Celery job framework.
Idempotent so environments that already created the table via earlier
runtime DDL experiments can still upgrade cleanly.
"""

from alembic import op

revision = "0002_gwapi_jobs"
down_revision = "0001_gwapi_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gwapi.jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL,
            tenant_id TEXT NOT NULL,
            schema_name TEXT,
            payload JSONB NOT NULL,
            result JSONB,
            error TEXT,
            side_effects JSONB NOT NULL DEFAULT '{}',
            progress JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            created_by TEXT,
            user_name TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_status_created
        ON gwapi.jobs (status, created_at)
        WHERE status = 'created'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_tenant
        ON gwapi.jobs (tenant_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gwapi.jobs")
