#!/usr/bin/env python3
"""Check ze-browser sidecar health.

Usage:
    python scripts/check_browser_health.py
    python scripts/check_browser_health.py http://localhost:8080
    python scripts/check_browser_health.py http://browser:8080 --timeout 10
    python scripts/check_browser_health.py --probe
    python scripts/check_browser_health.py --probe --probe-url https://example.com
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

_DEFAULT_PROBE_URL = "https://example.com"


def _normalize_base_url(address: str) -> str:
    base = address.rstrip("/")
    if "://" not in base:
        base = f"http://{base}"
    return base


def _request_json(
    url: str,
    *,
    timeout: float,
    method: str = "GET",
    body: dict | None = None,
) -> tuple[int, dict | str]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        try:
            payload: dict | str = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return resp.status, payload


def check_health(base_url: str, timeout: float) -> tuple[bool, str]:
    url = f"{_normalize_base_url(base_url)}/health"
    try:
        status, payload = _request_json(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} from {url}"
    except urllib.error.URLError as exc:
        return False, f"cannot reach {url}: {exc.reason}"
    except TimeoutError:
        return False, f"timed out after {timeout}s waiting for {url}"

    if status != 200:
        return False, f"unexpected status {status} from {url}"

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return False, f"unexpected payload from {url}: {payload!r}"

    return True, url


def check_probe(
    base_url: str,
    probe_url: str,
    timeout: float,
) -> tuple[bool, str]:
    url = f"{_normalize_base_url(base_url)}/extract"
    try:
        status, payload = _request_json(
            url,
            timeout=timeout,
            method="POST",
            body={"url": probe_url, "timeout_ms": int(timeout * 1000)},
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        return False, f"HTTP {exc.code} from {url}: {detail}"
    except urllib.error.URLError as exc:
        return False, f"cannot reach {url}: {exc.reason}"
    except TimeoutError:
        return False, f"timed out after {timeout}s waiting for extract of {probe_url!r}"

    if status != 200:
        return False, f"unexpected status {status} from {url}"

    if not isinstance(payload, dict):
        return False, f"invalid JSON from {url}: {payload!r}"

    page_status = payload.get("status_code")
    text = payload.get("text") or ""
    title = payload.get("title") or ""

    if page_status != 200:
        return False, (
            f"extract of {probe_url!r} returned page status {page_status!r} "
            f"(title={title!r})"
        )

    if not text.strip():
        return False, f"extract of {probe_url!r} returned empty text (title={title!r})"

    return True, f"{probe_url} → {len(text)} chars, {title!r}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check ze-browser sidecar GET /health (optional POST /extract probe).",
    )
    parser.add_argument(
        "address",
        nargs="?",
        default="http://localhost:8080",
        help="Sidecar base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Health check timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Also POST /extract against a real page (launches Chromium)",
    )
    parser.add_argument(
        "--probe-url",
        default=_DEFAULT_PROBE_URL,
        help=f"URL to extract when --probe is set (default: {_DEFAULT_PROBE_URL})",
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=45.0,
        help="Extract probe timeout in seconds (default: 45)",
    )
    args = parser.parse_args()

    ok, detail = check_health(args.address, args.timeout)
    if not ok:
        print(f"fail: {detail}", file=sys.stderr)
        raise SystemExit(1)

    print(f"ok ({detail})")

    if not args.probe:
        raise SystemExit(0)

    ok, detail = check_probe(args.address, args.probe_url, args.probe_timeout)
    if not ok:
        print(f"fail: probe {detail}", file=sys.stderr)
        raise SystemExit(1)

    print(f"ok probe ({detail})")


if __name__ == "__main__":
    main()
