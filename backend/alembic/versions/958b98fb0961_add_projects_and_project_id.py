"""add_projects_and_project_id

Revision ID: 958b98fb0961
Revises: be543e5d3be3
Create Date: 2026-07-23 10:00:39.550996

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '958b98fb0961'
down_revision = 'be543e5d3be3'
branch_labels = None
depends_on = None


_SCOPED = [
    "assets", "competitor_entities", "coverage_snapshots", "domain_lexicon",
    "grid_cells", "insights", "mapping_cards", "observations", "reports",
]


def upgrade() -> None:
    # 1. projects table.
    op.create_table('projects',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    # 2. Seed a default project ONLY if any scoped table already has data, so
    #    existing rows have somewhere to belong. Fresh DBs skip this.
    conn = op.get_bind()
    has_data = False
    for t in _SCOPED:
        if (conn.execute(sa.text(f"SELECT 1 FROM {t} LIMIT 1")).first()):
            has_data = True
            break
    default_pid = None
    if has_data:
        default_pid = conn.execute(sa.text(
            "INSERT INTO projects (name, category, description) "
            "VALUES ('默认项目', '', '迁移前的历史数据') RETURNING id"
        )).scalar()

    # 3. Add project_id as NULLABLE, backfill existing rows, then set NOT NULL.
    for t in _SCOPED:
        op.add_column(t, sa.Column('project_id', sa.UUID(), nullable=True))
        if default_pid is not None:
            conn.execute(
                sa.text(f"UPDATE {t} SET project_id = :pid WHERE project_id IS NULL"),
                {"pid": str(default_pid)},
            )
        op.alter_column(t, 'project_id', nullable=False)
        op.create_index(op.f(f'ix_{t}_project_id'), t, ['project_id'], unique=False)
        op.create_foreign_key(f'fk_{t}_project', t, 'projects', ['project_id'], ['id'])

    # 4. Swap global unique constraints for project-scoped ones.
    op.drop_constraint('competitor_entities_canonical_name_key', 'competitor_entities', type_='unique')
    op.create_unique_constraint('uq_competitor_project_name', 'competitor_entities', ['project_id', 'canonical_name'])
    op.drop_constraint('grid_cells_cell_key_key', 'grid_cells', type_='unique')
    op.create_unique_constraint('uq_cell_project_key', 'grid_cells', ['project_id', 'cell_key'])


def downgrade() -> None:
    op.drop_constraint('uq_cell_project_key', 'grid_cells', type_='unique')
    op.create_unique_constraint('grid_cells_cell_key_key', 'grid_cells', ['cell_key'])
    op.drop_constraint('uq_competitor_project_name', 'competitor_entities', type_='unique')
    op.create_unique_constraint('competitor_entities_canonical_name_key', 'competitor_entities', ['canonical_name'])
    for t in _SCOPED:
        op.drop_constraint(f'fk_{t}_project', t, type_='foreignkey')
        op.drop_index(op.f(f'ix_{t}_project_id'), table_name=t)
        op.drop_column(t, 'project_id')
    op.drop_table('projects')
