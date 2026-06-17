from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExportManifest:
    exported_at: datetime
    domains: list[str]
