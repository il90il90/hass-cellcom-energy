"""Quick test: CustomerInit with a real access token.

Usage:
    python _research/test_customer_init.py <access_token>

Tries three strategies and reports the HTTP status + response for each.
"""
import asyncio
import sys
import json
import uuid
import aiohttp

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""

BASE_URL = "https://digital-api.cellcom.co.il"
ENDPOINT = "/api/General/CustomerInit"
CLIENT_ID = "c3e851e4-1e58-11ea-a26b-0242ac130004"


def _device_id() -> str:
    raw = uuid.uuid4().hex
    return f"{raw[:6]}-{raw[6:9]}-{raw[9:12]}-{raw[12:16]}-{raw[16:28]}"


def _session_id() -> str:
    raw = uuid.uuid4().hex
    return f"{raw[:7]}-{raw[7:11]}-{raw[11:15]}-{raw[15:17]}-{raw[17:29]}"


HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "ClientID": CLIENT_ID,
    "Content-Type": "application/json",
    "DeviceId": _device_id(),
    "Origin": "https://cellcom.co.il",
    "Referer": "https://cellcom.co.il/",
    "SessionID": _session_id(),
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Authorization": f"Bearer {TOKEN}",
}

PRIME_URLS = [
    "https://cellcom.co.il/",
    "https://digital-api.cellcom.co.il/",
    "https://cellcom.co.il/my-cellcom/",
]

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
}


async def run() -> None:
    if not TOKEN or not TOKEN.startswith("eyJ"):
        print("ERROR: pass the JWT access token as first argument")
        sys.exit(1)

    connector = aiohttp.TCPConnector(ssl=True)
    async with aiohttp.ClientSession(connector=connector) as session:

        # ── Strategy 1: cold request (no priming) ─────────────────────────────
        print("\n── Strategy 1: cold PUT (no priming) ──")
        try:
            async with session.put(
                BASE_URL + ENDPOINT,
                headers=HEADERS,
                json={},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                print(f"  HTTP {resp.status}")
                if resp.status == 200:
                    data = json.loads(text)
                    print(f"  ReturnCode: {data.get('Header', {}).get('ReturnCode')}")
                    print(f"  Keys: {list(data.keys())}")
                else:
                    print(f"  Body[:200]: {text[:200]}")
        except Exception as e:
            print(f"  Exception: {e}")

        # ── Strategy 2: prime session first ───────────────────────────────────
        print("\n── Strategy 2: prime session then PUT ──")
        for url in PRIME_URLS:
            try:
                async with session.get(
                    url, headers=BROWSER_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=15),
                    allow_redirects=True,
                ) as r:
                    print(f"  prime {url} → HTTP {r.status}")
            except Exception as e:
                print(f"  prime {url} → ERROR: {e}")

        try:
            async with session.put(
                BASE_URL + ENDPOINT,
                headers=HEADERS,
                json={},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                print(f"  PUT HTTP {resp.status}")
                if resp.status == 200:
                    data = json.loads(text)
                    rc = data.get("Header", {}).get("ReturnCode")
                    msg = data.get("Header", {}).get("ReturnCodeMessage", "")
                    print(f"  ReturnCode: {rc}  msg: {msg}")
                    sbp = data.get("Body", {}).get("subscribersByProduct", {})
                    print(f"  subscribersByProduct keys: {list(sbp.keys())}")
                    energy = sbp.get("Energy", [])
                    print(f"  Energy subscribers: {len(energy)}")
                    if energy:
                        s = energy[0]
                        print(f"  BAN: {s.get('ban')}  status: {s.get('productStatus')}")
                else:
                    print(f"  Body[:300]: {text[:300]}")
        except Exception as e:
            print(f"  Exception: {e}")


asyncio.run(run())
