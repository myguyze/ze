#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from ze_api.db import create_pool, dispose_pool
from ze_onboarding import ResetService
from ze_api.settings import Settings


async def _run(scope: str, confirm: str) -> None:
    settings = Settings()
    pool = await create_pool(settings)
    try:
        service = ResetService(pool)
        result = await service.reset(scope, confirm=confirm)
    finally:
        await dispose_pool(pool)

    if not result.deleted:
        print("Nothing was deleted.")
        return
    for table, count in result.deleted.items():
        print(f"{table}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset learned Ze personal state.")
    parser.add_argument(
        "--scope",
        choices=["memory", "personal_state"],
        default="personal_state",
    )
    parser.add_argument("--confirm", required=True, help="Must be RESET")
    args = parser.parse_args()

    asyncio.run(_run(args.scope, args.confirm))


if __name__ == "__main__":
    main()
