"""projects, teams, datasets, job configs, tasks, jobs, submissions and reviews

Revision ID: 8d3f0b6e1a27
Revises: 5c1e9a7d2b40
Create Date: 2026-10-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8d3f0b6e1a27'
down_revision: Union[str, Sequence[str], None] = '5c1e9a7d2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('projects',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('data_classification', sa.String(length=16), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_projects_owner_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects')),
    sa.UniqueConstraint('code', name=op.f('uq_projects_code'))
    )
    op.create_table('teams',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_teams_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teams')),
    sa.UniqueConstraint('code', name=op.f('uq_teams_code'))
    )
    op.create_table('dataset_versions',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False),
    sa.Column('checksum', sa.String(length=80), nullable=False),
    sa.Column('item_count', sa.Integer(), nullable=False),
    sa.Column('item_type', sa.String(length=32), nullable=False),
    sa.Column('parser', sa.String(length=64), nullable=False),
    sa.Column('parser_options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('parser_version', sa.String(length=32), nullable=False),
    sa.Column('parse_report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_dataset_versions_created_by_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_dataset_versions_project_id_projects')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_versions')),
    sa.UniqueConstraint('project_id', 'version', name='uq_dataset_versions')
    )
    op.create_table('guideline_versions',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_guideline_versions_created_by_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_guideline_versions_project_id_projects')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_guideline_versions')),
    sa.UniqueConstraint('project_id', 'version', name='uq_guideline_versions')
    )
    op.create_table('job_configs',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('item_type', sa.String(length=32), nullable=False),
    sa.Column('label_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('job_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('self_check', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_job_configs_created_by_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_job_configs_project_id_projects')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_configs')),
    sa.UniqueConstraint('project_id', 'version', name='uq_job_configs')
    )
    op.create_table('project_members',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_by', sa.Uuid(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], name=op.f('fk_project_members_assigned_by_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_members_project_id_projects')),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_project_members_role_id_roles')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_project_members_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_members'))
    )
    op.create_index(op.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False)
    op.create_index('uq_project_members_active', 'project_members', ['project_id', 'user_id', 'role_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_table('project_teams',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_by', sa.Uuid(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], name=op.f('fk_project_teams_assigned_by_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_teams_project_id_projects')),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_project_teams_team_id_teams')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_teams'))
    )
    op.create_index(op.f('ix_project_teams_project_id'), 'project_teams', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_teams_team_id'), 'project_teams', ['team_id'], unique=False)
    op.create_index('uq_project_teams_active', 'project_teams', ['project_id', 'team_id'], unique=True, postgresql_where=sa.text('removed_at IS NULL'))
    op.create_table('reason_codes',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('default_severity', sa.String(length=16), nullable=False),
    sa.Column('applies_to', sa.String(length=16), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_reason_codes_project_id_projects')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reason_codes')),
    sa.UniqueConstraint('project_id', 'code', name='uq_reason_codes')
    )
    op.create_table('team_members',
    sa.Column('team_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('team_role', sa.String(length=16), nullable=False),
    sa.Column('is_lead', sa.Boolean(), nullable=False),
    sa.Column('added_by', sa.Uuid(), nullable=True),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('remove_reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_team_members_added_by_users')),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_team_members_team_id_teams')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_team_members_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_team_members'))
    )
    op.create_index(op.f('ix_team_members_team_id'), 'team_members', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_members_user_id'), 'team_members', ['user_id'], unique=False)
    op.create_index('uq_team_members_active', 'team_members', ['team_id', 'user_id'], unique=True, postgresql_where=sa.text('removed_at IS NULL'))
    op.create_index('uq_team_members_lead', 'team_members', ['team_id'], unique=True, postgresql_where=sa.text('is_lead AND removed_at IS NULL'))
    op.create_table('items',
    sa.Column('dataset_version_id', sa.Uuid(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('external_ref', sa.String(length=200), nullable=True),
    sa.Column('item_type', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], name=op.f('fk_items_dataset_version_id_dataset_versions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_items'))
    )
    op.create_index('ix_items_dataset_ordinal', 'items', ['dataset_version_id', 'ordinal'], unique=False)
    op.create_table('tasks',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('dataset_version_id', sa.Uuid(), nullable=False),
    sa.Column('job_config_id', sa.Uuid(), nullable=False),
    sa.Column('guideline_version_id', sa.Uuid(), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('signed_off_by', sa.Uuid(), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_tasks_created_by_users')),
    sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], name=op.f('fk_tasks_dataset_version_id_dataset_versions')),
    sa.ForeignKeyConstraint(['guideline_version_id'], ['guideline_versions.id'], name=op.f('fk_tasks_guideline_version_id_guideline_versions')),
    sa.ForeignKeyConstraint(['job_config_id'], ['job_configs.id'], name=op.f('fk_tasks_job_config_id_job_configs')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_tasks_project_id_projects')),
    sa.ForeignKeyConstraint(['signed_off_by'], ['users.id'], name=op.f('fk_tasks_signed_off_by_users')),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_tasks_team_id_teams')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tasks'))
    )
    op.create_index(op.f('ix_tasks_project_id'), 'tasks', ['project_id'], unique=False)
    op.create_index(op.f('ix_tasks_team_id'), 'tasks', ['team_id'], unique=False)
    op.create_table('jobs',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('guideline_version_id', sa.Uuid(), nullable=False),
    sa.Column('job_config_id', sa.Uuid(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('assignee_id', sa.Uuid(), nullable=True),
    sa.Column('reviewer_id', sa.Uuid(), nullable=True),
    sa.Column('last_reviewer_id', sa.Uuid(), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rework_count', sa.Integer(), nullable=False),
    sa.Column('has_unsure', sa.Boolean(), nullable=False),
    sa.Column('is_gold', sa.Boolean(), nullable=False),
    sa.Column('draft', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('draft_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], name=op.f('fk_jobs_assignee_id_users')),
    sa.ForeignKeyConstraint(['guideline_version_id'], ['guideline_versions.id'], name=op.f('fk_jobs_guideline_version_id_guideline_versions')),
    sa.ForeignKeyConstraint(['job_config_id'], ['job_configs.id'], name=op.f('fk_jobs_job_config_id_job_configs')),
    sa.ForeignKeyConstraint(['last_reviewer_id'], ['users.id'], name=op.f('fk_jobs_last_reviewer_id_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_jobs_project_id_projects')),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_jobs_reviewer_id_users')),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_jobs_task_id_tasks')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs'))
    )
    op.create_index('ix_jobs_assignee_status', 'jobs', ['assignee_id', 'status'], unique=False)
    op.create_index('ix_jobs_project_status', 'jobs', ['project_id', 'status'], unique=False)
    op.create_index('ix_jobs_reviewer_status', 'jobs', ['reviewer_id', 'status'], unique=False)
    op.create_index('ix_jobs_task_status_created', 'jobs', ['task_id', 'status', 'created_at'], unique=False)
    op.create_table('job_items',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_job_items_item_id_items')),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_job_items_job_id_jobs')),
    sa.PrimaryKeyConstraint('job_id', 'item_id', name=op.f('pk_job_items'))
    )
    op.create_index(op.f('ix_job_items_item_id'), 'job_items', ['item_id'], unique=False)
    op.create_table('submissions',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('round', sa.Integer(), nullable=False),
    sa.Column('annotator_id', sa.Uuid(), nullable=False),
    sa.Column('self_check_result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['annotator_id'], ['users.id'], name=op.f('fk_submissions_annotator_id_users')),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_submissions_job_id_jobs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_submissions')),
    sa.UniqueConstraint('job_id', 'round', name='uq_submissions_round')
    )
    op.create_index(op.f('ix_submissions_job_id'), 'submissions', ['job_id'], unique=False)
    op.create_table('annotations',
    sa.Column('submission_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('target', sa.String(length=64), nullable=True),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_unsure', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_annotations_item_id_items')),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], name=op.f('fk_annotations_submission_id_submissions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_annotations'))
    )
    op.create_index(op.f('ix_annotations_submission_id'), 'annotations', ['submission_id'], unique=False)
    op.create_table('reviews',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('submission_id', sa.Uuid(), nullable=True),
    sa.Column('reviewer_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('supersedes_review_id', sa.Uuid(), nullable=True),
    sa.Column('decision', sa.String(length=24), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('guideline_issue', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_reviews_job_id_jobs')),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_reviews_reviewer_id_users')),
    sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], name=op.f('fk_reviews_submission_id_submissions')),
    sa.ForeignKeyConstraint(['supersedes_review_id'], ['reviews.id'], name=op.f('fk_reviews_supersedes_review_id_reviews')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reviews'))
    )
    op.create_index(op.f('ix_reviews_job_id'), 'reviews', ['job_id'], unique=False)
    op.create_table('review_errors',
    sa.Column('review_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('target', sa.String(length=64), nullable=True),
    sa.Column('reason_code', sa.String(length=64), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_review_errors_item_id_items')),
    sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], name=op.f('fk_review_errors_review_id_reviews')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review_errors'))
    )
    op.create_index(op.f('ix_review_errors_review_id'), 'review_errors', ['review_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_review_errors_review_id'), table_name='review_errors')
    op.drop_table('review_errors')
    op.drop_index(op.f('ix_reviews_job_id'), table_name='reviews')
    op.drop_table('reviews')
    op.drop_index(op.f('ix_annotations_submission_id'), table_name='annotations')
    op.drop_table('annotations')
    op.drop_index(op.f('ix_submissions_job_id'), table_name='submissions')
    op.drop_table('submissions')
    op.drop_index(op.f('ix_job_items_item_id'), table_name='job_items')
    op.drop_table('job_items')
    op.drop_index('ix_jobs_task_status_created', table_name='jobs')
    op.drop_index('ix_jobs_reviewer_status', table_name='jobs')
    op.drop_index('ix_jobs_project_status', table_name='jobs')
    op.drop_index('ix_jobs_assignee_status', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_tasks_team_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_project_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index('ix_items_dataset_ordinal', table_name='items')
    op.drop_table('items')
    op.drop_index('uq_team_members_lead', table_name='team_members', postgresql_where=sa.text('is_lead AND removed_at IS NULL'))
    op.drop_index('uq_team_members_active', table_name='team_members', postgresql_where=sa.text('removed_at IS NULL'))
    op.drop_index(op.f('ix_team_members_user_id'), table_name='team_members')
    op.drop_index(op.f('ix_team_members_team_id'), table_name='team_members')
    op.drop_table('team_members')
    op.drop_table('reason_codes')
    op.drop_index('uq_project_teams_active', table_name='project_teams', postgresql_where=sa.text('removed_at IS NULL'))
    op.drop_index(op.f('ix_project_teams_team_id'), table_name='project_teams')
    op.drop_index(op.f('ix_project_teams_project_id'), table_name='project_teams')
    op.drop_table('project_teams')
    op.drop_index('uq_project_members_active', table_name='project_members', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_project_id'), table_name='project_members')
    op.drop_table('project_members')
    op.drop_table('job_configs')
    op.drop_table('guideline_versions')
    op.drop_table('dataset_versions')
    op.drop_table('teams')
    op.drop_table('projects')
