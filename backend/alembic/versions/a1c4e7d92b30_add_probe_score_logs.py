"""add probe_score_logs

Revision ID: a1c4e7d92b30
Revises: 9ff74a4d4e2b
Create Date: 2026-07-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1c4e7d92b30'
down_revision = '9ff74a4d4e2b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'probe_score_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('cell_id', sa.UUID(), nullable=False),
        sa.Column('competitor_id', sa.UUID(), nullable=False),
        sa.Column('probe_cycle', sa.Integer(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=True),
        sa.Column('has_image', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('evidence_type', sa.String(), nullable=True),
        sa.Column('scored_by', sa.String(), nullable=True),
        sa.Column('score_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('scored_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['cell_id'], ['grid_cells.id'], ),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitor_entities.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_probe_score_logs_project_id', 'probe_score_logs', ['project_id'])
    op.create_index('ix_probe_score_logs_cell_id', 'probe_score_logs', ['cell_id'])
    op.create_index('ix_probe_score_logs_competitor_id', 'probe_score_logs', ['competitor_id'])


def downgrade() -> None:
    op.drop_index('ix_probe_score_logs_competitor_id', table_name='probe_score_logs')
    op.drop_index('ix_probe_score_logs_cell_id', table_name='probe_score_logs')
    op.drop_index('ix_probe_score_logs_project_id', table_name='probe_score_logs')
    op.drop_table('probe_score_logs')
