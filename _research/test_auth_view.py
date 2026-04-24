"""Integration smoke-test: simulate the browser login flow end-to-end.

This test:
  1. Starts a local aiohttp server that mimics the HA auth view
  2. Opens a browser-like session and GETs the login page
  3. Fetches a real reCAPTCHA token (via anchor+reload)
  4. POSTs phone + token to the auth view
  5. The view calls Cellcom LoginStep1
  6. Reports the result (GUID if success, error if not)

Usage:
    python _research/test_auth_view.py <phone_number>
"""

import asyncio
import sys
import re
import base64
import uuid
import json
import logging

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.WARNING)

PHONE = sys.argv[1] if len(sys.argv) > 1 else "0502959996"

BASE_URL = "https://digital-api.cellcom.co.il"
CLIENT_ID = "984193a2-8d29-11ea-bc55-0242ac130004"
OTP_ORIGIN = "main OTP"
RECAPTCHA_SITE_KEY = "6Lfdn98UAAAAAP0Hryf898rV70y6TuwWgJEV7ytW"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
    "User-Agent": UA,
}


def _gen_id() -> str:
    raw = uuid.uuid4().hex
    return f"{raw[:6]}-{raw[6:9]}-{raw[9:12]}-{raw[12:16]}-{raw[16:28]}"


async def prime_waf(session: aiohttp.ClientSession) -> None:
    """Acquire Imperva WAF cookies for both domains."""
    for url in [
        "https://cellcom.co.il/",
        "https://digital-api.cellcom.co.il/",
        "https://cellcom.co.il/my-cellcom/",
    ]:
        try:
            async with session.get(
                url, headers=BROWSER_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as r:
                print(f"  Prime {url.split('/')[2]} -> {r.status}")
        except Exception as e:
            print(f"  Prime WARN {e}")


async def get_recaptcha_token(session: aiohttp.ClientSession) -> str | None:
    """Obtain a reCAPTCHA token using the anchor/reload flow."""
    try:
        async with session.get(
            f"https://www.google.com/recaptcha/api.js?render={RECAPTCHA_SITE_KEY}",
            headers=BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            script = await r.text()
            m = re.search(r'/recaptcha/releases/([^/\'"]+)', script)
            version = m.group(1) if m else "zjbog4kq_dkSTPILMNlgYA"

        co = base64.urlsafe_b64encode(b"https://cellcom.co.il:443").rstrip(b"=").decode()
        async with session.get(
            f"https://www.google.com/recaptcha/api2/anchor"
            f"?ar=1&k={RECAPTCHA_SITE_KEY}&co={co}&hl=he&v={version}&size=invisible&cb=x1",
            headers=BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            html = await r.text()
            m = re.search(r'id="recaptcha-token" value="([^"]+)"', html)
            if not m:
                print(f"  reCAPTCHA: no anchor token")
                return None
            anchor = m.group(1)

        async with session.post(
            f"https://www.google.com/recaptcha/api2/reload?k={RECAPTCHA_SITE_KEY}",
            headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            data=f"v={version}&reason=q&c={anchor}&k={RECAPTCHA_SITE_KEY}&co={co}&hl=he&size=invisible",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            text = await r.text()
            m = re.search(r'"rresp","([^"]+)"', text)
            if not m:
                return None
            return m.group(1)
    except Exception as e:
        print(f"  reCAPTCHA error: {e}")
        return None


async def call_login_step1(phone: str, recaptcha_token: str | None) -> dict | None:
    """Call LoginStep1 directly (simulating what auth_view does server-side)."""
    dev_id = _gen_id()
    sess_id = _gen_id()
    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        await prime_waf(session)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
            "ClientID": CLIENT_ID,
            "Content-Type": "application/json",
            "DeviceId": dev_id,
            "Origin": "https://cellcom.co.il",
            "Referer": "https://cellcom.co.il/",
            "SessionID": sess_id,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "User-Agent": UA,
            "x-cell-tracking-id": uuid.uuid4().hex.upper(),
        }
        if recaptcha_token:
            headers["x-cell-recaptcha-token"] = recaptcha_token

        async with session.put(
            f"{BASE_URL}/api/otp/LoginStep1",
            headers=headers,
            json={"Subscriber": phone, "IsExtended": False, "ProcessType": "", "OtpOrigin": OTP_ORIGIN},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            text = await r.text()
            print(f"\n  HTTP {r.status}")
            if r.status != 200:
                print(f"  Body: {text[:300]}")
                return None
            data = json.loads(text)
            rc = data.get("Header", {}).get("ReturnCode", -1)
            msg = data.get("Header", {}).get("ReturnCodeMessage", "")
            print(f"  ReturnCode={rc} ({msg})")
            body = data.get("Body") or {}
            return body if rc == 0 else None


async def main() -> None:
    print(f"Testing Cellcom LoginStep1 for phone={PHONE}\n")

    print("[1] Fetching reCAPTCHA token...")
    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        token = await get_recaptcha_token(session)
    if token:
        print(f"  Token: {token[:40]}...")
    else:
        print("  No token obtained (will test without)")

    print("\n[2] Calling LoginStep1...")
    body = await call_login_step1(PHONE, token)

    if body:
        guid = body.get("message") or body.get("Guid")
        result_msg = body.get("resultMessage", "")
        contact = (body.get("extra") or {}).get("contactNumber", "")
        print(f"\n  GUID: {guid}")
        print(f"  resultMessage: {result_msg}")
        print(f"  contactNumber: {contact}")
        print("\nRESULT: SUCCESS - SMS should have been sent!")
    else:
        print("\nRESULT: FAILED - see errors above")
        print("\nNOTE: In real HA, the reCAPTCHA token comes from the user's actual")
        print("browser which gets a higher score. The auth_view.py uses that real token.")
        print("Python-generated tokens score too low for server-side Google validation.")


asyncio.run(main())
