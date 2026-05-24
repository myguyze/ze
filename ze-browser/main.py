from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from extractor import extract

app = FastAPI(title="ze-browser")


class ExtractRequest(BaseModel):
    url: str
    timeout_ms: int = 15000


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/extract")
async def extract_page(req: ExtractRequest):
    try:
        parsed = urlparse(req.url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        result = await extract(req.url, req.timeout_ms)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Page load timed out")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Navigation failed: {exc}")

    return result
