"""identity, rbac and audit tables with role/permission seed

Revision ID: 5c1e9a7d2b40
Revises: 2241605d377c
Create Date: 2026-10-30 18:00:00.000000

The seed reads app.core.rbac_catalog as it is at this revision. Later changes to the
matrix must ship as a new migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core import rbac_catalog as catalog


# revision identifiers, used by Alembic.
revision: str = '5c1e9a7d2b40'
down_revision: Union[str, Sequence[str], None] = '2241605d377c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('audit_events',
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_name', sa.String(length=200), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target_type', sa.String(length=64), nullable=False),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('project_id', sa.Uuid(), nullable=True),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index('ix_audit_events_actor_created', 'audit_events', ['actor_id', 'created_at'], unique=False)
    op.create_index('ix_audit_events_project_created', 'audit_events', ['project_id', 'created_at'], unique=False)
    op.create_index('ix_audit_events_target', 'audit_events', ['target_type', 'target_id'], unique=False)
    permissions = op.create_table('permissions',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('resource', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_permissions')),
    sa.UniqueConstraint('code', name=op.f('uq_permissions_code'))
    )
    roles = op.create_table('roles',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('code', 'scope', name='uq_roles_code_scope')
    )
    op.create_table('users',
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('employee_code', sa.String(length=64), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('employment_type', sa.String(length=16), nullable=False),
    sa.Column('joined_at', sa.Date(), nullable=True),
    sa.Column('left_at', sa.Date(), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('employee_code', name=op.f('uq_users_employee_code'))
    )
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('replaced_by_id', sa.Uuid(), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['replaced_by_id'], ['refresh_tokens.id'], name=op.f('fk_refresh_tokens_replaced_by_id_refresh_tokens')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    role_conflicts = op.create_table('role_conflicts',
    sa.Column('role_a_id', sa.Uuid(), nullable=False),
    sa.Column('role_b_id', sa.Uuid(), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=False),
    sa.Column('effect', sa.String(length=16), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['role_a_id'], ['roles.id'], name=op.f('fk_role_conflicts_role_a_id_roles')),
    sa.ForeignKeyConstraint(['role_b_id'], ['roles.id'], name=op.f('fk_role_conflicts_role_b_id_roles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_role_conflicts'))
    )
    role_permissions = op.create_table('role_permissions',
    sa.Column('role_id', sa.Uuid(), nullable=False),
    sa.Column('permission_id', sa.Uuid(), nullable=False),
    sa.Column('limit_scope', sa.String(length=16), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], name=op.f('fk_role_permissions_permission_id_permissions')),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_role_permissions_role_id_roles')),
    sa.PrimaryKeyConstraint('role_id', 'permission_id', name=op.f('pk_role_permissions'))
    )
    role_requirements = op.create_table('role_requirements',
    sa.Column('project_role_id', sa.Uuid(), nullable=False),
    sa.Column('required_platform_role_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['project_role_id'], ['roles.id'], name=op.f('fk_role_requirements_project_role_id_roles')),
    sa.ForeignKeyConstraint(['required_platform_role_id'], ['roles.id'], name=op.f('fk_role_requirements_required_platform_role_id_roles')),
    sa.PrimaryKeyConstraint('project_role_id', 'required_platform_role_id', name=op.f('pk_role_requirements'))
    )
    op.create_table('user_action_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_action_tokens_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_action_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_action_tokens_token_hash'))
    )
    op.create_index('uq_user_action_tokens_open', 'user_action_tokens', ['user_id', 'purpose'], unique=True, postgresql_where=sa.text('used_at IS NULL'))
    op.create_table('user_platform_roles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role_id', sa.Uuid(), nullable=False),
    sa.Column('granted_by', sa.Uuid(), nullable=True),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by', sa.Uuid(), nullable=True),
    sa.Column('revoke_reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['granted_by'], ['users.id'], name=op.f('fk_user_platform_roles_granted_by_users')),
    sa.ForeignKeyConstraint(['revoked_by'], ['users.id'], name=op.f('fk_user_platform_roles_revoked_by_users')),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_user_platform_roles_role_id_roles')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_platform_roles_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_platform_roles'))
    )
    op.create_index(op.f('ix_user_platform_roles_user_id'), 'user_platform_roles', ['user_id'], unique=False)
    op.create_index('uq_user_platform_roles_active', 'user_platform_roles', ['user_id', 'role_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))

    seed(roles, permissions, role_permissions, role_requirements, role_conflicts)


def seed(roles, permissions, role_permissions, role_requirements, role_conflicts) -> None:
    op.bulk_insert(roles, [
        {"id": r.id, "code": str(r.code), "scope": str(r.scope), "name": r.name,
         "description": r.description, "is_system": True}
        for r in catalog.ROLES
    ])
    op.bulk_insert(permissions, [
        {"id": p.id, "code": str(p.code), "resource": p.resource, "action": p.action,
         "level": str(p.level), "description": p.description}
        for p in catalog.PERMISSIONS
    ])
    op.bulk_insert(role_permissions, [
        {"role_id": catalog.role_id(scope, code), "permission_id": catalog.permission_id(perm),
         "limit_scope": str(limit)}
        for (scope, code), grants in catalog.ROLE_PERMISSIONS.items()
        for perm, limit in grants.items()
    ])
    op.bulk_insert(role_requirements, [
        {"project_role_id": catalog.role_id(catalog.RoleScope.PROJECT, project_role),
         "required_platform_role_id": catalog.role_id(catalog.RoleScope.PLATFORM, platform_role)}
        for project_role, platform_role in catalog.ROLE_REQUIREMENTS.items()
    ])
    op.bulk_insert(role_conflicts, [
        {"id": catalog.role_id("conflict", f"{c.role_a}:{c.role_b}"),
         "role_a_id": catalog.role_id(*c.role_a), "role_b_id": catalog.role_id(*c.role_b),
         "scope": str(c.scope), "effect": str(c.effect)}
        for c in catalog.ROLE_CONFLICTS
    ])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_user_platform_roles_active', table_name='user_platform_roles', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index(op.f('ix_user_platform_roles_user_id'), table_name='user_platform_roles')
    op.drop_table('user_platform_roles')
    op.drop_index('uq_user_action_tokens_open', table_name='user_action_tokens', postgresql_where=sa.text('used_at IS NULL'))
    op.drop_table('user_action_tokens')
    op.drop_table('role_requirements')
    op.drop_table('role_permissions')
    op.drop_table('role_conflicts')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('permissions')
    op.drop_index('ix_audit_events_target', table_name='audit_events')
    op.drop_index('ix_audit_events_project_created', table_name='audit_events')
    op.drop_index('ix_audit_events_actor_created', table_name='audit_events')
    op.drop_table('audit_events')
