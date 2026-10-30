import hashlib
import re
import uuid
from datetime import datetime
from typing import Any

from app.core.clock import Clock, utcnow
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.storage import Storage
from app.domain.parsers import ParseResult, ParserOptionsError, get_parser, parse_failed
from app.models.project import DatasetVersion, Item
from app.models.user import User
from app.repositories.project import ProjectRepository
from app.repositories.work import WorkRepository
from app.services.audit import AuditService

PREVIEW_ITEMS = 5
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


def upload_prefix(project_id: uuid.UUID) -> str:
    return f"projects/{project_id}/uploads/"


class DatasetService:
    def __init__(
        self,
        projects: ProjectRepository,
        work: WorkRepository,
        storage: Storage,
        audit: AuditService,
        clock: Clock = utcnow,
    ) -> None:
        self.projects = projects
        self.work = work
        self.storage = storage
        self.audit = audit
        self.clock = clock

    async def upload_url(self, project_id: uuid.UUID, filename: str, size: int) -> tuple[str, str]:
        if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise FileTooLargeError(f"File is larger than {settings.MAX_UPLOAD_MB} MB")
        safe = _SAFE_NAME.sub("_", filename)[-80:] or "data.jsonl"
        key = f"{upload_prefix(project_id)}{uuid.uuid4().hex}-{safe}"
        url = await self.storage.presign_put(key, "application/octet-stream")
        return key, url

    async def _load(self, project_id: uuid.UUID, upload_key: str) -> bytes:
        if not upload_key.startswith(upload_prefix(project_id)) or ".." in upload_key:
            raise AppError("Upload not found", code="upload_not_found")
        size = await self.storage.size(upload_key)
        if size is None:
            raise AppError("Upload not found; upload the file first", code="upload_not_found")
        if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise FileTooLargeError(f"File is larger than {settings.MAX_UPLOAD_MB} MB")
        return await self.storage.read(upload_key)

    def _parser(self, name: str):
        parser = get_parser(name)
        if parser is None:
            raise AppError(f"Unknown parser {name}", code="parser_not_found")
        return parser

    def _run(self, parser, data: bytes, options: dict[str, str], limit: int | None) -> ParseResult:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AppError("File must be UTF-8 text", code="parse_failed") from None
        try:
            return parser.parse(text.splitlines(), options, limit)
        except ParserOptionsError as exc:
            raise AppError(str(exc), code="invalid_parser_options") from None

    async def preview(
        self, project_id: uuid.UUID, upload_key: str, parser_name: str, options: dict[str, str]
    ) -> dict[str, Any]:
        parser = self._parser(parser_name)
        data = await self._load(project_id, upload_key)
        result = self._run(parser, data, options, PREVIEW_ITEMS * 4)
        return {
            "items": [
                {"ordinal": i.ordinal, "external_ref": i.external_ref, "payload": i.payload}
                for i in result.items[:PREVIEW_ITEMS]
            ],
            "report": result.report(),
            "options": {**parser.default_options, **options},
        }

    async def create(
        self,
        actor: User,
        project_id: uuid.UUID,
        upload_key: str,
        parser_name: str,
        options: dict[str, str],
    ) -> DatasetVersion:
        parser = self._parser(parser_name)
        data = await self._load(project_id, upload_key)
        result = self._run(parser, data, options, None)
        if parse_failed(result):
            raise AppError(
                "Too many lines failed to parse",
                code="parse_failed",
                details={"parse_report": result.report()},
            )
        version = await self.projects.next_version(DatasetVersion, project_id)
        dataset = await self.projects.add(
            DatasetVersion(
                id=uuid.uuid4(),
                project_id=project_id,
                version=version,
                storage_path=upload_key,
                checksum="sha256:" + hashlib.sha256(data).hexdigest(),
                item_count=len(result.items),
                item_type=parser.item_type,
                parser=parser.name,
                parser_options={**parser.default_options, **options},
                parser_version=parser.version,
                parse_report=result.report(),
                created_by=actor.id,
            )
        )
        await self.projects.add_items(
            [
                Item(
                    id=uuid.uuid4(),
                    dataset_version_id=dataset.id,
                    ordinal=i.ordinal,
                    external_ref=i.external_ref,
                    item_type=parser.item_type,
                    payload=i.payload,
                )
                for i in result.items
            ]
        )
        await self.audit.record(
            actor=actor,
            action="dataset.create",
            target_type="dataset_version",
            target_id=dataset.id,
            project_id=project_id,
            after={"version": version, "items": dataset.item_count, "checksum": dataset.checksum},
        )
        return dataset

    async def get(self, project_id: uuid.UUID, version: int) -> DatasetVersion:
        dataset = await self.projects.dataset(project_id, version)
        if dataset is None:
            raise NotFoundError("Dataset version not found")
        return dataset

    async def delete(
        self, actor: User, project_id: uuid.UUID, version: int, now: datetime | None = None
    ) -> None:
        dataset = await self.get(project_id, version)
        if any(t.dataset_version_id == dataset.id for t in await self.work.tasks(project_id)):
            raise ConflictError("A task uses this dataset version", code="dataset_in_use")
        dataset.deleted_at = now or self.clock()
        await self.audit.record(
            actor=actor,
            action="dataset.delete",
            target_type="dataset_version",
            target_id=dataset.id,
            project_id=project_id,
            before={"version": version},
        )
