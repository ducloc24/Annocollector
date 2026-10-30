"""appeals, gold answers, system settings; reviews.reviewer_id becomes optional

Revision ID: a4c7e2d19b53
Revises: 8d3f0b6e1a27
Create Date: 2026-10-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a4c7e2d19b53'
down_revision: Union[str, Sequence[str], None] = '8d3f0b6e1a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('system_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_system_settings_updated_by_users')),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_system_settings'))
    )
    op.create_table('gold_answers',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('target', sa.String(length=64), nullable=True),
    sa.Column('expected', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_gold_answers_item_id_items')),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_gold_answers_job_id_jobs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_gold_answers')),
    sa.UniqueConstraint('job_id', 'item_id', 'target', name='uq_gold_answers')
    )
    op.create_index(op.f('ix_gold_answers_job_id'), 'gold_answers', ['job_id'], unique=False)
    op.create_table('appeals',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('review_id', sa.Uuid(), nullable=False),
    sa.Column('opened_by', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('resolved_by', sa.Uuid(), nullable=True),
    sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_appeals_job_id_jobs')),
    sa.ForeignKeyConstraint(['opened_by'], ['users.id'], name=op.f('fk_appeals_opened_by_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_appeals_project_id_projects')),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], name=op.f('fk_appeals_resolved_by_users')),
    sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], name=op.f('fk_appeals_review_id_reviews')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appeals'))
    )
    op.create_index(op.f('ix_appeals_job_id'), 'appeals', ['job_id'], unique=False)
    op.create_index(op.f('ix_appeals_project_id'), 'appeals', ['project_id'], unique=False)
    op.alter_column('reviews', 'reviewer_id', existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM reviews WHERE reviewer_id IS NULL")
    op.alter_column('reviews', 'reviewer_id', existing_type=sa.Uuid(), nullable=False)
    op.drop_index(op.f('ix_appeals_project_id'), table_name='appeals')
    op.drop_index(op.f('ix_appeals_job_id'), table_name='appeals')
    op.drop_table('appeals')
    op.drop_index(op.f('ix_gold_answers_job_id'), table_name='gold_answers')
    op.drop_table('gold_answers')
    op.drop_table('system_settings')
