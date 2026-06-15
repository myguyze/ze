"""
DB outcome verification for Ze eval scenarios.

Runs declarative checks against Ze's database after a scenario executes,
then cleans up eval-created rows so runs don't contaminate each other.

Scenario YAML format:

    verify:
      - table: user_reminders
        where:
          label__icontains: dentist   # case-insensitive substring
          sent: false                 # exact match
        expect: exists                # 'exists' or 'not_exists'
        cleanup: true                 # delete matching rows after check (default: true)

Requires DATABASE_URL env var (same as Ze).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import asyncpg


@dataclass
class VerifyResult:
    table: str
    where: dict
    expect: str
    actual_count: int
    passed: bool
    error: str | None = None

    def summary(self) -> str:
        conds = ", ".join(f"{k}={v!r}" for k, v in self.where.items())
        status = "PASS" if self.passed else "FAIL"
        return f"{status} {self.table}({conds}) expect={self.expect} got={self.actual_count}"


def _build_where(where: dict) -> tuple[str, list]:
    """Build a parameterised WHERE clause from a condition dict."""
    if not where:
        return "TRUE", []
    clauses: list[str] = []
    params: list = []
    i = 1
    for key, value in where.items():
        if key.endswith("__icontains"):
            col = key[: -len("__icontains")]
            clauses.append(f"{col} ILIKE ${i}")
            params.append(f"%{value}%")
        else:
            if value is True:
                clauses.append(f"{key} = TRUE")
            elif value is False:
                clauses.append(f"{key} = FALSE")
            else:
                clauses.append(f"{key} = ${i}")
                params.append(value)
                i += 1
            continue
        i += 1
    return " AND ".join(clauses), params


async def _check(conn: asyncpg.Connection, check: dict) -> VerifyResult:
    table = check["table"]
    where = check.get("where", {})
    expect = check.get("expect", "exists")
    where_sql, params = _build_where(where)

    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table} WHERE {where_sql}", *params)
    count = int(count)

    if expect == "exists":
        passed = count > 0
    elif expect == "not_exists":
        passed = count == 0
    else:
        passed = False

    return VerifyResult(
        table=table,
        where=where,
        expect=expect,
        actual_count=count,
        passed=passed,
    )


async def _cleanup(conn: asyncpg.Connection, check: dict) -> None:
    table = check["table"]
    where = check.get("where", {})
    if not where:
        return
    where_sql, params = _build_where(where)
    await conn.execute(f"DELETE FROM {table} WHERE {where_sql}", *params)


async def run_verification(checks: list[dict], db_url: str | None = None) -> list[VerifyResult]:
    """
    Run all checks then clean up eval-created rows.
    Returns one VerifyResult per check.
    """
    url = db_url or os.environ.get("DATABASE_URL", "postgresql://ze:ze@localhost:5432/ze")
    results: list[VerifyResult] = []

    try:
        conn = await asyncpg.connect(url)
    except Exception as exc:
        return [
            VerifyResult(
                table=c.get("table", "?"),
                where=c.get("where", {}),
                expect=c.get("expect", "exists"),
                actual_count=0,
                passed=False,
                error=f"DB connection failed: {exc}",
            )
            for c in checks
        ]

    try:
        for check in checks:
            try:
                result = await _check(conn, check)
                results.append(result)
                if check.get("cleanup", True):
                    await _cleanup(conn, check)
            except Exception as exc:
                results.append(VerifyResult(
                    table=check.get("table", "?"),
                    where=check.get("where", {}),
                    expect=check.get("expect", "exists"),
                    actual_count=0,
                    passed=False,
                    error=str(exc),
                ))
    finally:
        await conn.close()

    return results


def outcome_correct(results: list[VerifyResult]) -> bool:
    """True only if every check passed."""
    return bool(results) and all(r.passed for r in results)
