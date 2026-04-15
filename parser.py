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
    # Adding default values makes these "optional" during validation
    date: str = "Unknown" 
    time: str = "Unknown"
    transaction_id: str = "N/A"
    amount: Optional[float] = 0
    client_id: Optional[str] = None
    remaining_balance: Optional[float] = 0
    transaction_type: Optional[str] = "Unknown"
    transaction_status: str = "PENDING" # Provide a sensible default


class ParseResult(BaseModel):
    records: List[TransactionDescription]
    metadata: Dict[str, Any] = {}


def _parse_local(text: str) -> ParseResult:
    items: List[TransactionDescription] = []
    # Simplified regex to find amounts
    for m in re.finditer(r"(\b[0-9]+(?:\.[0-9]{1,2})\b)", text):
        amount = float(m.group(1))
        
        # We MUST provide the required fields defined in TransactionDescription
        items.append(TransactionDescription(
            date="0000-00-00",        # Required by your model
            time="00:00",              # Required by your model
            transaction_id="LOCAL",    # Required by your model
            transaction_status="UNKNOWN", # Required by your model
            amount=amount,
            transaction_type="Fallback"
        ))

    return ParseResult(records=items, metadata={"parser": "local", "count": len(items)})


def _parse_with_groq(text: str) -> ParseResult:
    """Use Groq API to parse text using patterns derived from receipt_parser.js."""
    if Groq is None:
        raise RuntimeError("groq client not installed")

    api_key = os.getenv("GROQ_API_KEY")
    # Using a capable model for logic and pattern matching
    model = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768") 
    
    client = Groq(api_key=api_key)

    # Define the tool schema
    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_transaction_data",
                "description": "Extract structured transaction details from raw receipt text.",
                "parameters": ParseResult.model_json_schema(),
            },
        }
    ]

    # --- ENHANCED PROMPT INTEGRATING KNOWN PATTERNS ---
    system_instruction = (
        "You are a precise financial data extraction engine. Extract transaction details from the provided text "
        "using these specific pattern guidelines derived from legacy regex parsers:\n\n"
        
        "### 1. DATE & TIME NORMALIZATION\n"
        "- **Date Patterns**: Recognize [DD/MM/YYYY], [YYYY-MM-DD], and [DD-MMM-YYYY] (e.g., 10-Jan-2024). "
        "Normalize all dates to ISO format: YYYY-MM-DD.\n"
        "- **Time Patterns**: Look for 24h or 12h formats. Always normalize to 12-hour format with AM/PM "
        "(e.g., '14:30:05' becomes '02:30:05 PM').\n\n"
        
        "### 2. TRANSACTION MAPPING\n"
        "- **Type**: Categorize into [AEPS Withdrawal, AEPS Deposit, AEPS Mini Statement, AEPS Balance Enquiry, Money Transfer, Fund Transfer, Third Party Deposit]. "
        "Look for keywords like 'CASH_WITHDRAWAL', 'ON-US Cash Deposit', or 'Money Transfer'.\n"
        "- **Status**: Map keywords like 'SUCCESSFUL' or 'TXN SUCCESS' to 'SUCCESS'. Map 'FAIL', 'DECLINED', or 'REJECTED' to 'FAILED'.\n\n"
        
        "### 3. SENSITIVE DATA & IDS\n"
        "- **Transaction ID**: Prioritize STAN, RRN, or Txn ID. If the ID is longer than 6 digits, extract the full ID "
        "but note that the primary identifier is often the last 6 digits.\n"
        "- **Client ID**: Identify Aadhaar/VID or Account Numbers. Maintain masking if present.\n\n"
        
        "### 4. FINANCIAL DATA\n"
        "- **Amount**: Extract numeric values only. Ignore 'Rs.', 'INR', or currency symbols. "
        "Differentiate between 'Transaction Amount' and 'Remaining/Account Balance'.\n\n"
        
        "Strictly return the data using the 'extract_transaction_data' function."
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"Receipt Text:\n{text}"}
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "extract_transaction_data"}},
        temperature=0,
    )

    # Parsing the tool response
    tool_call = completion.choices[0].message.tool_calls[0]
    import json
    data = json.loads(tool_call.function.arguments)

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
