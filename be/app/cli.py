"""Operational commands.

    uv run python -m app.cli create-hr-admin --email hr@company.vn --name "Nguyễn Văn A"

``create-hr-admin`` bootstraps the very first hr_admin, since nobody can grant roles before
one exists. It refuses to run once an active hr_admin is present.
"""

import argparse
import asyncio
import getpass
import sys
import uuid

from app.core.clock import utcnow
from app.core.rbac_catalog import PlatformRole, RoleScope
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.rbac import UserPlatformRole
from app.models.user import EmploymentType, User, UserStatus
from app.repositories.audit import AuditRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.services.audit import AuditService
from app.services.auth import validate_new_password


async def create_hr_admin(email: str, full_name: str, password: str) -> None:
    validate_new_password(password)
    async with SessionLocal() as session:
        rbac = RbacRepository(session)
        users = UserRepository(session)
        role = await rbac.get_role(RoleScope.PLATFORM, PlatformRole.HR_ADMIN)
        if role is None:
            raise SystemExit("Role catalog is missing; run `npm run db:migrate` first.")
        now = utcnow()
        if await rbac.count_active_holders(role.id, now) > 0:
            raise SystemExit("An active hr_admin already exists; grant roles through the API.")
        normalized = email.strip().lower()
        if await users.get_by_email(normalized):
            raise SystemExit(f"{normalized} already exists.")

        user = await users.add(
            User(
                id=uuid.uuid4(),
                email=normalized,
                full_name=full_name.strip(),
                employment_type=EmploymentType.FULL_TIME,
                status=UserStatus.ACTIVE,
                password_hash=hash_password(password),
                token_version=0,
            )
        )
        assignment = await rbac.add_assignment(
            UserPlatformRole(id=uuid.uuid4(), user_id=user.id, role_id=role.id, granted_at=now)
        )
        audit = AuditService(AuditRepository(session))
        await audit.record(
            actor=None,
            action="user.create",
            target_type="user",
            target_id=user.id,
            after={"email": user.email, "full_name": user.full_name},
            reason="bootstrap via CLI",
        )
        await audit.record(
            actor=None,
            action="platform_role.grant",
            target_type="platform_role",
            target_id=assignment.id,
            after={"user_id": str(user.id), "role": role.code},
            reason="bootstrap via CLI",
        )
        await session.commit()
    await engine.dispose()
    print(f"Created hr_admin {normalized}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("create-hr-admin", help="create the first hr_admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    if args.command == "create-hr-admin":
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
        asyncio.run(create_hr_admin(args.email, args.name, password))


if __name__ == "__main__":
    main()
