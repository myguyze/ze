import pytest
from ze_calendar.timezone.service import TimezoneService


@pytest.fixture
def svc():
    return TimezoneService()


def test_resolve_alias(svc):
    assert svc.resolve("London") == "Europe/London"
    assert svc.resolve("london") == "Europe/London"
    assert svc.resolve("NYC") == "America/New_York"
    assert svc.resolve("São Paulo") == "America/Sao_Paulo"


def test_resolve_raw_iana(svc):
    assert svc.resolve("Europe/Paris") == "Europe/Paris"
    assert svc.resolve("Asia/Tokyo") == "Asia/Tokyo"


def test_resolve_unknown_raises(svc):
    with pytest.raises(ValueError, match="Unknown timezone"):
        svc.resolve("Narnia")


def test_now_in_returns_aware_datetime(svc):
    from datetime import datetime, timezone
    dt = svc.now_in("London")
    assert dt.tzinfo is not None


def test_now_in_utc(svc):
    from datetime import timezone
    dt = svc.now_in("UTC")
    assert str(dt.tzinfo) in ("UTC", "UTC+00:00")
