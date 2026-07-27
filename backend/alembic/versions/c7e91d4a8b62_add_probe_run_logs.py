"""add probe_run_logs

Revision ID: c7e91d4a8b62
Revises: a1c4e7d92b30
Create Date: 2026-07-27 18:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7e91d4a8b62"
down_revision = "a1c4e7d92b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "probe_run_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("cell_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("probe_cycle", sa.Integer(), nullable=True),
        sa.Column("strategy_version", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("final_state", sa.String(), nullable=True),
        sa.Column(
            "candidates_found", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("scored_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("passed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "persisted_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("search_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("browser_pages", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("scoring_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "agentic_model_calls", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source_budgets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agentic_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agentic_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["cell_id"], ["grid_cells.id"]),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitor_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_probe_run_logs_project_id", "probe_run_logs", ["project_id"])
    op.create_index("ix_probe_run_logs_cell_id", "probe_run_logs", ["cell_id"])
    op.create_index(
        "ix_probe_run_logs_competitor_id", "probe_run_logs", ["competitor_id"]
    )
    op.create_index(
        "ix_probe_run_logs_strategy_version", "probe_run_logs", ["strategy_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_probe_run_logs_strategy_version", table_name="probe_run_logs")
    op.drop_index("ix_probe_run_logs_competitor_id", table_name="probe_run_logs")
    op.drop_index("ix_probe_run_logs_cell_id", table_name="probe_run_logs")
    op.drop_index("ix_probe_run_logs_project_id", table_name="probe_run_logs")
    op.drop_table("probe_run_logs")
