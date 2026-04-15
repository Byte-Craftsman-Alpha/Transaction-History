"""Modular parser utilities for TransactionMonitoring.

Provides a pluggable parser that tries a Groq backend (if configured)
and falls back to a simple local parser. Exposes a `parse_text`
function that returns a Pydantic model instance.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

try:
    from groq import Groq
except Exception:  # pragma: no cover - optional dependency
    Groq = None


class TransactionDescription(BaseModel):
    date: str
    time: str
    transaction_id: str
    amount: Optional[float] = 0
    client_id: Optional[str] = None
    remaining_balance: Optional[float] = 0
    transaction_type: Optional[str] = "Unknown"
    transaction_status: str


class ParseResult(BaseModel):
    records: List[TransactionDescription]
    metadata: Dict[str, Any] = {}


def _parse_local(text: str) -> ParseResult:
    """A lightweight fallback parser that extracts currency amounts and nearby words.

    This is intentionally simple: it finds tokens that look like prices (e.g. 12.50)
    and associates the nearest preceding word as the name.
    """
    items: List[TransactionDescription] = []
    # find all amounts
    for m in re.finditer(r"(\b[0-9]+(?:\.[0-9]{1,2})\b)", text):
        amount = float(m.group(1))
        # attempt to get a preceding word (naive)
        start = max(0, m.start() - 50)
        snippet = text[start:m.start()]
        # take last word-like token
        names = re.findall(r"([A-Za-z\-]{2,})", snippet)
        name = names[-1] if names else "unknown"
        items.append(TransactionDescription(key=name, value=amount))

    return ParseResult(records=items, metadata={"parser": "local", "count": len(items)})


def _parse_with_groq(text: str) -> ParseResult:
    """Use Groq API to parse text into the `ParseResult` schema.

    Requires `GROQ_API_KEY` and `GROQ_MODEL` environment variables to be set.
    If the groq client isn't installed or environment variables are missing,
    raises RuntimeError so the caller can fall back.
    """
    if Groq is None:
        raise RuntimeError("groq client not installed")

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct-0905")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    client = Groq(api_key=api_key)

    # create tools schema from our Pydantic model
    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_structured",
                "description": "Extract structured records from text",
                "parameters": ParseResult.model_json_schema(),
            },
        }
    ]

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": """
You are a helpful assistant that extracts structured information of an ONLINE transaction from raw text.
You have to exctract the following information:
- date of the transaction in ISO format (YYYY-MM-DD) patterns: [DD/MM/YYY, DD-MM-YY]
- Time of the transaction in 24-hour format (HH:MM) patterns: [HH:MM:SS AM/PM, HH:MM:SS, HH:MM AM/PM, HH:MM]
- Transaction ID (usually a 12-15 digit number) pattern: [############]
- Amount (in float, without currency symbols and is optional if not present in the text) pattern: [##.##]
- Client ID (Aadhar number, Account Number or similar) patterns: [####-####-####, #### #### ####, ############]
- Remaining Balance (in float, without currency symbols and is optional if not present in the text) pattern: [##.##]
- Transaction Type (e.g. Withdrawal, Deposit, Third Party Deposit, Transfer, Balance Enquiry, Other)
- Transaction Status (e.g. SUCCESS, FAILED)
"""
            },
            {
                "role": "user",
                "content": text
            },
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "extract_structured"}},
        temperature=0,
    )

    tool_call = completion.choices[0].message.tool_calls[0]
    # `function.arguments` should be a JSON string/object matching ParseResult
    args = tool_call.function.arguments
    # allow either dict or JSON string
    if isinstance(args, str):
        import json

        data = json.loads(args)
    else:
        data = args

    # Validate and return
    return ParseResult.model_validate(data)


def parse_text(text: str, prefer_backend: Optional[str] = None) -> ParseResult:
    """Parse `text` into a `ParseResult`.

    prefer_backend: optional string 'groq' or 'local' to force backend.
    By default tries Groq first (if available), otherwise falls back to local parser.
    """
    start = time.time()
    # backend selection
    backend_order = [prefer_backend] if prefer_backend else ["groq", "local"]

    last_exc: Optional[Exception] = None
    for backend in backend_order:
        if backend == "groq":
            try:
                result = _parse_with_groq(text)
                result.metadata["duration_ms"] = int((time.time() - start) * 1000)
                return result
            except Exception as e:
                last_exc = e
                continue

        if backend == "local":
            try:
                result = _parse_local(text)
                result.metadata["duration_ms"] = int((time.time() - start) * 1000)
                return result
            except Exception as e:
                last_exc = e
                continue

    # if we reach here, raise the last exception
    raise last_exc or RuntimeError("No parser backends available")


if __name__ == "__main__":
    # quick manual test
    sample = "I bought coffee 5.50 and a donut 2.00 yesterday"
    print(parse_text(sample).model_dump_json(indent=2))
