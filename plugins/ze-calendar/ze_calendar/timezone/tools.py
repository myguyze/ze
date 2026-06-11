from ze_core.orchestration.tool import ToolAccess, tool
from ze_calendar.timezone.service import TimezoneService


@tool(access=ToolAccess.READ, description=(
    "Return the current local time in one or more cities or IANA timezone names. "
    "Pass a list of city names or timezone strings (e.g. ['London', 'Tokyo', 'UTC'])."
))
async def world_time(
    timezone_service: TimezoneService,
    locations: list[str],
) -> list[dict]:
    results = []
    for loc in locations:
        try:
            dt = timezone_service.now_in(loc)
            results.append({
                "location": loc,
                "iana":     timezone_service.resolve(loc),
                "time":     dt.strftime("%Y-%m-%d %H:%M"),
                "tz_abbr":  dt.strftime("%Z"),
                "utc_offset": dt.strftime("%z"),
            })
        except (ValueError, KeyError) as e:
            results.append({"location": loc, "error": str(e)})
    return results
