from __future__ import annotations

import zoneinfo
from datetime import datetime

_ALIASES: dict[str, str] = {
    "london":        "Europe/London",
    "lisbon":        "Europe/Lisbon",
    "paris":         "Europe/Paris",
    "berlin":        "Europe/Berlin",
    "new york":      "America/New_York",
    "nyc":           "America/New_York",
    "los angeles":   "America/Los_Angeles",
    "la":            "America/Los_Angeles",
    "chicago":       "America/Chicago",
    "toronto":       "America/Toronto",
    "são paulo":     "America/Sao_Paulo",
    "sao paulo":     "America/Sao_Paulo",
    "dubai":         "Asia/Dubai",
    "mumbai":        "Asia/Kolkata",
    "delhi":         "Asia/Kolkata",
    "singapore":     "Asia/Singapore",
    "hong kong":     "Asia/Hong_Kong",
    "shanghai":      "Asia/Shanghai",
    "beijing":       "Asia/Shanghai",
    "tokyo":         "Asia/Tokyo",
    "seoul":         "Asia/Seoul",
    "sydney":        "Australia/Sydney",
    "melbourne":     "Australia/Melbourne",
    "auckland":      "Pacific/Auckland",
    "utc":           "UTC",
    "gmt":           "UTC",
}


class TimezoneService:

    def resolve(self, name: str) -> str:
        """Return the IANA key for a common city or timezone alias.

        Falls back to treating `name` as a raw IANA key if not in the alias table.
        Raises ValueError if the key is unrecognised by zoneinfo.
        """
        iana = _ALIASES.get(name.lower(), name)
        try:
            zoneinfo.ZoneInfo(iana)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Unknown timezone or city: {name!r}")
        return iana

    def now_in(self, tz_name: str) -> datetime:
        """Return the current wall-clock time in the given timezone."""
        tz = zoneinfo.ZoneInfo(self.resolve(tz_name))
        return datetime.now(tz)

    def convert(self, dt: datetime, to_tz: str) -> datetime:
        """Convert a timezone-aware datetime to a different timezone."""
        tz = zoneinfo.ZoneInfo(self.resolve(to_tz))
        return dt.astimezone(tz)

    def format(self, dt: datetime, tz_name: str, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
        """Format a UTC datetime as a local time string in the given timezone."""
        return self.convert(dt, tz_name).strftime(fmt)
