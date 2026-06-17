from __future__ import annotations

import base64
import json
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile


def _default(obj: object) -> object:
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


class ExportAssembler:
    """Builds the ZIP archive from domain data collected by DataPortabilityService."""

    def build(
        self,
        domain_data: dict[str, list],
        exported_at: datetime,
    ) -> bytes:
        manifest = {
            "exported_at": exported_at.isoformat(),
            "domains": list(domain_data.keys()),
        }

        buf = BytesIO()
        with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for name, rows in domain_data.items():
                dicts = _rows_to_dicts(rows)
                zf.writestr(f"{name}.json", json.dumps(dicts, indent=2, default=_default))

        return buf.getvalue()
