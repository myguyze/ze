from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExportManifest:
    exported_at: datetime
    schema_revisions: list[str]
    domains: list[str]


@dataclass
class ImportResult:
    domains_imported: list[str]
    rows_imported: dict[str, int]
