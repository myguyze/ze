"""Ze API CLI — one-off admin commands."""
from __future__ import annotations

import asyncio
import sys


async def _register_gmail_push() -> None:
    import os
    from ze_api.settings import get_settings
    from ze_google.auth import GoogleCredentials
    from ze_google.gmail_channel import GmailChannel

    settings = get_settings()
    public_url = settings.public_url or os.environ.get("PUBLIC_URL", "")
    topic = settings.gmail_pubsub_topic

    if not public_url:
        print("ERROR: PUBLIC_URL is not set in .env / environment.", file=sys.stderr)
        sys.exit(1)
    if not topic:
        print("ERROR: GMAIL_PUBSUB_TOPIC is not set in .env / environment.", file=sys.stderr)
        sys.exit(1)

    creds = GoogleCredentials.from_settings(settings)
    if creds is None:
        print("ERROR: Google credentials not configured.", file=sys.stderr)
        sys.exit(1)

    channel = GmailChannel(credentials=creds, public_url=public_url)
    await channel.register_push(topic)
    print(f"Gmail push registered. Topic: {topic}")
    print(f"Webhook URL: {public_url.rstrip('/')}/api/v0/webhooks/email")
    print("Note: watch expires after 7 days. Renew via the weekly renewal job or re-run this command.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m ze_api.cli", description="Ze API admin commands")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("register_gmail_push", help="Register Gmail inbox watch via Cloud Pub/Sub")

    args = parser.parse_args()
    if args.command == "register_gmail_push":
        asyncio.run(_register_gmail_push())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
