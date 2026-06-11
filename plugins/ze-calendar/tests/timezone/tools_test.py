import pytest
from ze_calendar.timezone.tools import world_time
from ze_calendar.timezone.service import TimezoneService


@pytest.fixture
def svc():
    return TimezoneService()


async def test_world_time_known_locations(svc):
    results = await world_time(timezone_service=svc, locations=["London", "Tokyo", "UTC"])
    assert len(results) == 3
    for r in results:
        assert "error" not in r
        assert "time" in r
        assert "iana" in r
        assert "utc_offset" in r


async def test_world_time_unknown_location(svc):
    results = await world_time(timezone_service=svc, locations=["Narnia"])
    assert len(results) == 1
    assert "error" in results[0]
    assert results[0]["location"] == "Narnia"


async def test_world_time_mixed(svc):
    results = await world_time(timezone_service=svc, locations=["London", "Narnia"])
    assert len(results) == 2
    london = next(r for r in results if r["location"] == "London")
    narnia = next(r for r in results if r["location"] == "Narnia")
    assert "time" in london
    assert "error" in narnia
