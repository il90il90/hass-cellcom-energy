"""Test all data endpoints with a real token."""
import asyncio
import aiohttp
import json
import uuid
import base64
import sys

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
BASE = "https://digital-api.cellcom.co.il"


def make_headers(token: str) -> dict:
    payload_b64 = token.split(".")[1] + "=="
    payload = json.loads(base64.b64decode(payload_b64))
    client_id = payload.get("CLIENT_ID", "")
    raw = uuid.uuid4().hex
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "he-IL,he;q=0.9",
        "ClientID": client_id,
        "Content-Type": "application/json",
        "DeviceId": f"{raw[:6]}-{raw[6:9]}-{raw[9:12]}-{raw[12:16]}-{raw[16:28]}",
        "Origin": "https://cellcom.co.il",
        "Referer": "https://cellcom.co.il/",
        "SessionID": f"{raw[:7]}-{raw[7:11]}-{raw[11:15]}-{raw[15:19]}-{raw[19:31]}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/147.0.0.0",
        "Authorization": f"Bearer {token}",
    }


async def run() -> None:
    if not TOKEN.startswith("eyJ"):
        print("Pass JWT as first argument")
        sys.exit(1)

    h = make_headers(TOKEN)
    print(f"ClientID: {h['ClientID']}\n")

    async with aiohttp.ClientSession() as sess:
        # Step 1: InvoiceData — get invoice list + billing info
        async with sess.get(BASE + "/api/SelfCare/InvoiceData", headers=h, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            data = await resp.json(content_type=None)
            b = data.get("Body", {})
            invoices = b.get("invoices", [])
            print(f"InvoiceData HTTP {resp.status}  invoices={len(invoices)}")
            print(f"  Body keys: {list(b.keys())}")
            # Print full invoice list
            for i, inv in enumerate(invoices):
                print(f"  invoice[{i}]: {json.dumps(inv, ensure_ascii=False)[:200]}")

        print()
        # Step 2: if we got invoice ID, try Ibill endpoints
        if invoices:
            first = invoices[0]
            print("First invoice raw:", json.dumps(first, ensure_ascii=False, indent=2))


asyncio.run(run())
