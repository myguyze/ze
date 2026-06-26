from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from ze_api.api.dependencies import get_container, require_api_key
from ze_api.api.schemas import ActivityHeatmapResponse, AgentDayCount, HeatmapDay

router = APIRouter(tags=["activity"], dependencies=[Depends(require_api_key)])

_SQL = """
SELECT
    date_trunc('day', created_at AT TIME ZONE 'UTC')::date AS day,
    trace->>'agent'                                          AS agent,
    COUNT(*)::int                                            AS count
FROM messages
WHERE role = 'assistant'
  AND trace IS NOT NULL
  AND trace->>'agent' IS NOT NULL
  AND created_at >= $1
  AND created_at < $2 + INTERVAL '1 day'
GROUP BY 1, 2
ORDER BY 1 ASC, 3 DESC
"""


@router.get(
    "/activity/heatmap",
    response_model=ActivityHeatmapResponse,
    operation_id="getActivityHeatmap",
    summary="Agent activity heatmap",
    description=(
        "Returns per-day, per-agent assistant message counts for the given date range "
        "(defaults to rolling 12 months). Suitable for rendering a calendar heatmap."
    ),
)
async def get_activity_heatmap(
    start: date | None = Query(default=None, description="Start date inclusive (ISO date). Defaults to 12 months ago."),
    end: date | None = Query(default=None, description="End date inclusive (ISO date). Defaults to today."),
    container=Depends(get_container),
) -> ActivityHeatmapResponse:
    today = datetime.now(tz=timezone.utc).date()
    end_date = end or today
    start_date = start or (end_date - timedelta(days=365))

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc)

    async with container.pool.acquire() as conn:
        rows = await conn.fetch(_SQL, start_dt, end_dt)

    by_day: dict[str, list[AgentDayCount]] = defaultdict(list)
    all_agents: set[str] = set()

    for row in rows:
        day_str = row["day"].isoformat()
        agent = row["agent"]
        count = row["count"]
        by_day[day_str].append(AgentDayCount(agent=agent, count=count))
        all_agents.add(agent)

    days = [
        HeatmapDay(date=day, total=sum(a.count for a in agents), agents=agents)
        for day, agents in sorted(by_day.items())
    ]

    return ActivityHeatmapResponse(
        days=days,
        agents=sorted(all_agents),
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )
