from __future__ import annotations

import base64
import json
import re
from datetime import datetime, date, timezone
from decimal import Decimal
from io import BytesIO
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

_ISO_DT_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _export_default(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Not JSON-serializable: {type(obj)!r}")


def _rows_to_dicts(rows: list) -> list[dict]:
    return [dict(r) for r in rows]


def _coerce_value(v: object) -> object:
    """Parse ISO datetime strings back to datetime objects during import."""
    if isinstance(v, str) and _ISO_DT_PREFIX.match(v):
        try:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return v


def _coerce_row(row: dict) -> dict:
    return {k: _coerce_value(v) for k, v in row.items()}


class ExportAssembler:
    """Builds the ZIP archive from domain data collected by DataPortabilityService."""

    def build(
        self,
        domain_data: dict[str, list],
        exported_at: datetime,
        schema_revisions: list[str],
    ) -> bytes:
        manifest = {
            "exported_at": exported_at.isoformat(),
            "schema_revisions": sorted(schema_revisions),
            "domains": list(domain_data.keys()),
        }

        buf = BytesIO()
        with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for name, rows in domain_data.items():
                dicts = _rows_to_dicts(rows)
                zf.writestr(
                    f"{name}.json",
                    json.dumps(dicts, indent=2, default=_export_default),
                )

        return buf.getvalue()


async def bulk_insert(conn, table: str, rows: list[dict]) -> int:
    """Generic bulk INSERT for a single table using an existing asyncpg connection."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    records = [[row.get(c) for c in cols] for row in rows]
    await conn.executemany(sql, records)
    return len(rows)


class ImportAssembler:
    """Reads a ZIP archive and yields domain data ready for insertion."""

    def parse(self, archive_bytes: bytes) -> tuple[dict, dict[str, list[dict]]]:
        """Returns (manifest, domain_data) where rows are coerced for asyncpg."""
        buf = BytesIO(archive_bytes)
        with ZipFile(buf, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            domain_data: dict[str, list[dict]] = {}
            for name in zf.namelist():
                if name == "manifest.json":
                    continue
                domain_name = name.removesuffix(".json")
                rows = json.loads(zf.read(name))
                domain_data[domain_name] = [_coerce_row(r) for r in rows]
        return manifest, domain_data
