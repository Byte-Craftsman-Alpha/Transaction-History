"""FastAPI server for TransactionMonitoring parser.

Features:
- POST /parse: accepts `text` and optional `user_agent` in JSON body.
- API key authentication via `X-API-Key` header, mapped to username from `api_keys.json`.
- CORS enabled for all origins (adjustable).
- Enforced max response timeout via environment `MAX_RESPONSE_SECONDS`.
- Graceful error handling and typed Pydantic models.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from parser import ParseResult, parse_text

API_KEYS_PATH = os.path.join(os.path.dirname(__file__), "api_keys.json")
MAX_SECONDS = int(os.getenv("MAX_RESPONSE_SECONDS", "10"))


class ParseRequest(BaseModel):
    text: str
    user_agent: Optional[str] = None


class ParseResponse(BaseModel):
    status: str
    user: str
    result: ParseResult
    processing_ms: int


def load_api_keys(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


api_keys = load_api_keys(API_KEYS_PATH)

app = FastAPI(title="TransactionMonitoring Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_api_user(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header")
    user = api_keys.get(x_api_key)
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return user


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": str(exc)},
    )


@app.post("/parse", response_model=ParseResponse)
async def parse_endpoint(req: ParseRequest, user: str = Depends(get_api_user)):
    start = time.time()

    # Use asyncio.wait_for to enforce timeout
    try:
        # parse_text may be sync; run in thread to avoid blocking
        loop = asyncio.get_running_loop()
        coro = loop.run_in_executor(None, parse_text, req.text)
        parse_result: ParseResult = await asyncio.wait_for(coro, timeout=MAX_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Parsing timed out after {MAX_SECONDS} seconds")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    processing_ms = int((time.time() - start) * 1000)
    return ParseResponse(status="ok", user=user, result=parse_result, processing_ms=processing_ms)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
