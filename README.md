# TransactionMonitoring Parser + FastAPI

This project exposes a modular parser and a FastAPI server to parse long text bodies into structured output.

Quick features
- Modular `Parser.py` with `parse_text(text)` that returns a Pydantic `ParseResult`.
- FastAPI server `server.py` with `/parse` endpoint.
- CORS enabled, API key authentication, max response timeout, and error handling.

Getting started

1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

2. Configure environment (optional)

- Create a `.env` with `GROQ_API_KEY` and `GROQ_MODEL` if you want to enable the Groq backend.
- Set `MAX_RESPONSE_SECONDS` to change the parse timeout (default 10).

3. API keys

Edit `api_keys.json` to add production API keys mapping to usernames.

4. Run server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Example request

```bash
curl -X POST http://localhost:8000/parse \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: test-api-key-123' \
  -d '{"text": "I bought coffee 5.50 and donut 2.00", "user_agent": "curl/7.XX"}'
```

```javascript
/**
 * Simple test script for the TransactionMonitoring API
 * Paste this into your browser console.
 */
const testParseAPI = async (text = "Dinner at Italian place 45.00", apiKey = "Device A") => {
    const apiBase = "https://transaction-history-iota.vercel.app"; // Adjust if your backend is on a different port
    
    console.log(`%c🚀 Sending request to ${apiBase}/parse...`, "color: #007bff; font-weight: bold;");

    try {
        const response = await fetch(`${apiBase}/parse`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': apiKey
            },
            body: JSON.stringify({ 
                text: text, 
                user_agent: navigator.userAgent 
            })
        });

        const data = await response.json();

        if (response.ok) {
            console.log("%c✅ Success!", "color: #28a745; font-weight: bold;");
            console.table(data); // Displays the JSON response in a nice table
        } else {
            console.error(`%c❌ API Error (${response.status}):`, "font-weight: bold;", data);
        }
    } catch (err) {
        console.error("%c🔥 Network/CORS Error:", "font-weight: bold; color: #dc3545;", err.message);
    }
};

// Execute immediately
testParseAPI();
```

Notes on production readiness
- Store API keys securely (vault/DB) — `api_keys.json` is only for demo.
- Use HTTPS behind a reverse proxy.
- Increase `uvicorn` workers for concurrency and tune worker class.
- Consider a stricter request size limit and rate limiting.

JavaScript Fetch demo

You can open [demo_fetch.html](demo_fetch.html) in a browser (serve the folder or open file://). It shows a minimal `fetch`-based example that calls the `/parse` endpoint and includes the `X-API-Key` header.

If you run the server locally on the same host and port, you can simply open the demo in the browser and press "Send". If the server is on a different origin, configure CORS or open the demo via a local static server like `python -m http.server 8001` and visit `http://localhost:8001/demo_fetch.html`.
