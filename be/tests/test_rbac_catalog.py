from app.core import rbac_catalog as c
from app.core.rbac_catalog import Limit, Perm, PlatformRole, ProjectRole, RoleScope

P, J = RoleScope.PLATFORM, RoleScope.PROJECT


def grants(scope: RoleScope, code: str) -> dict[Perm, Limit]:
    return c.ROLE_PERMISSIONS[(scope, code)]


def test_catalog_sizes():
    assert len(c.PERMISSIONS) == 27
    assert {p.code for p in c.PERMISSIONS} == set(Perm)
    assert len([r for r in c.ROLES if r.scope == P]) == 7
    assert len([r for r in c.ROLES if r.scope == J]) == 5


def test_every_role_has_a_matrix_entry_and_every_permission_is_used():
    assert {(r.scope, r.code) for r in c.ROLES} == set(c.ROLE_PERMISSIONS)
    used = {perm for g in c.ROLE_PERMISSIONS.values() for perm in g}
    assert used == set(Perm)


def test_permission_level_matches_role_scope():
    levels = {p.code: p.level for p in c.PERMISSIONS}
    for (scope, _), granted in c.ROLE_PERMISSIONS.items():
        for perm in granted:
            assert levels[perm] in (scope.value, "any"), (scope, perm)


def test_separation_of_duties():
    assert Perm.DATASET_READ not in grants(P, PlatformRole.HR_ADMIN)
    assert Perm.PLATFORM_ROLE_GRANT not in grants(P, PlatformRole.PLATFORM_ADMIN)
    assert Perm.JOB_REVIEW not in grants(J, ProjectRole.OWNER)
    assert grants(P, PlatformRole.HR_ADMIN)[Perm.AUDIT_READ] == Limit.RBAC


def test_ids_are_stable_and_unique():
    ids = [r.id for r in c.ROLES] + [p.id for p in c.PERMISSIONS]
    assert len(ids) == len(set(ids))
    assert c.role_id(P, "hr_admin") == c.role_id("platform", "hr_admin")


def test_platform_conflicts():
    assert c.platform_conflict("hr_admin", "platform_admin") == c.ConflictEffect.WARN
    assert c.platform_conflict("platform_admin", "hr_admin") == c.ConflictEffect.WARN
    assert c.platform_conflict("po", "annotator") is None
