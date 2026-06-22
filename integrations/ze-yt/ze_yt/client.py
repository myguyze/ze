from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from ze_logging import get_logger

log = get_logger(__name__)


class YtDlpClient:
    async def download_audio(self, url: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "audio.%(ext)s"
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--extract-audio",
                "--audio-format", "mp3",
                "--no-playlist",
                "-o", str(out),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"yt-dlp failed (exit {proc.returncode}): {stderr.decode()[:500]}"
                )
            mp3_files = list(Path(tmpdir).glob("*.mp3"))
            if not mp3_files:
                raise RuntimeError("yt-dlp produced no mp3 output")
            data = mp3_files[0].read_bytes()
            log.info("yt_dlp_downloaded", url=url, size=len(data))
            return data
