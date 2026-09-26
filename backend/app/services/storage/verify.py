"""
Compare what the database claims exists against what the storage root actually holds

It reports and never repairs: the repair differs per direction, and picking one silently is how data is lost
An orphaned object may be the only copy of a user's upload, and a row without an object may be a restore in progress
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.core.storage_keys import session_meta_key, tenant_meta_key, user_meta_key
from app.model.orm import File, Session, Tenant, User
from app.services.storage.meta import (
    RESERVED_FILENAMES,
    read_meta,
    session_meta_payload,
    tenant_meta_payload,
    user_meta_payload,
)

ORPHAN_KEY = "orphan_key"
MISSING_KEY = "missing_key"
STALE_META = "stale_meta"


@dataclass(frozen=True)
class Finding:
    kind: str
    key: str
    detail: str


@dataclass
class VerifyReport:
    findings: list[Finding] = field(default_factory=list)
    keys_on_disk: int = 0
    rows_in_database: int = 0
    breadcrumbs_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings

    def of_kind(self, kind: str) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]


def keys_on_disk() -> set[str]:
    """
    Every stored object under the tenants prefix, expressed as storage keys

    ? Reserved breadcrumbs and in-flight upload temps are never claimed by a row, so counting them would report permanent orphans
    """
    root = Path(config.data_dir).resolve()
    tenants = Path(config.tenants_dir).resolve()
    if not tenants.exists():
        return set()

    keys: set[str] = set()
    for path in tenants.rglob("*"):
        if not path.is_file():
            continue
        if path.name in RESERVED_FILENAMES or path.name.startswith(".upload-"):
            continue
        try:
            keys.add(path.resolve().relative_to(root).as_posix())
        except ValueError:
            # ! tenants_dir sits outside data_dir, so no key could name this object
            raise RuntimeError(f"tenants_dir {tenants} is not inside data_dir {root}") from None
    return keys


def _compare(key: str, expected: dict[str, object], kind_label: str) -> Optional[Finding]:
    found = read_meta(key)
    if found is None:
        return Finding(STALE_META, key, f"{kind_label} breadcrumb is missing or unreadable")
    differing = sorted(k for k in expected if found.get(k) != expected[k])
    if differing:
        return Finding(STALE_META, key, f"{kind_label} breadcrumb disagrees on {', '.join(differing)}")
    return None


async def verify(session: AsyncSession) -> VerifyReport:
    """
    Walk both directions and project every breadcrumb from its row

    The row is authoritative in all three checks, which is why a breadcrumb never becomes evidence about a file
    """
    report = VerifyReport()

    rows = (await session.execute(select(File.id, File.storage_key, File.filename))).all()
    claimed = {row.storage_key: row for row in rows}
    on_disk = keys_on_disk()
    report.rows_in_database = len(rows)
    report.keys_on_disk = len(on_disk)

    for key in sorted(on_disk - set(claimed)):
        report.findings.append(Finding(ORPHAN_KEY, key, "object on disk that no files row claims"))
    for key in sorted(set(claimed) - on_disk):
        report.findings.append(Finding(MISSING_KEY, key, f"files row {claimed[key].id} points at nothing on disk"))

    for tenant in (await session.execute(select(Tenant))).scalars():
        key = tenant_meta_key(str(tenant.id))
        report.breadcrumbs_checked += 1
        finding = _compare(
            key,
            tenant_meta_payload(
                tenant_id=str(tenant.id), slug=tenant.slug, name=tenant.name, created_at=tenant.created_at
            ),
            "tenant",
        )
        if finding:
            report.findings.append(finding)

    for user in (await session.execute(select(User))).scalars():
        key = user_meta_key(str(user.tenant_id), str(user.id))
        report.breadcrumbs_checked += 1
        finding = _compare(
            key,
            user_meta_payload(
                user_id=str(user.id),
                tenant_id=str(user.tenant_id),
                username=user.username,
                role=user.role,
                created_at=user.created_at,
            ),
            "user",
        )
        if finding:
            report.findings.append(finding)

    for chat in (await session.execute(select(Session).where(Session.deleted_at.is_(None)))).scalars():
        key = session_meta_key(str(chat.tenant_id), chat.user_id, str(chat.id))
        report.breadcrumbs_checked += 1
        finding = _compare(
            key,
            session_meta_payload(
                session_id=str(chat.id),
                tenant_id=str(chat.tenant_id),
                user_id=chat.user_id,
                created_at=chat.created_at,
            ),
            "session",
        )
        if finding:
            report.findings.append(finding)

    return report


def format_report(report: VerifyReport) -> str:
    """One line per finding, grouped by kind, with a summary that is readable when there is nothing wrong"""
    lines = [
        f"Storage root: {Path(config.data_dir).resolve()}",
        f"  objects on disk: {report.keys_on_disk}",
        f"  files rows:      {report.rows_in_database}",
        f"  breadcrumbs:     {report.breadcrumbs_checked}",
    ]
    if report.ok:
        lines.append("\nNo drift found.")
        return "\n".join(lines)

    for kind, heading in (
        (ORPHAN_KEY, "Objects with no row"),
        (MISSING_KEY, "Rows with no object"),
        (STALE_META, "Breadcrumbs that disagree with their row"),
    ):
        found = report.of_kind(kind)
        if not found:
            continue
        lines.append(f"\n{heading} ({len(found)}):")
        lines.extend(f"  {f.key}\n    {f.detail}" for f in found)

    lines.append(f"\n{len(report.findings)} finding(s). Nothing was repaired.")
    return "\n".join(lines)
