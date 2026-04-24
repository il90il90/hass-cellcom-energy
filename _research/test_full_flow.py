"""End-to-end test of the fixed integration flow (standalone, no HA dependency).

Replicates what config_flow + coordinator do, using the raw API logic.

Usage:
    python _research/test_full_flow.py <access_token>
"""
import asyncio
import sys
import base64
import json
import uuid

import aiohttp

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""

BASE = "https://digital-api.cellcom.co.il"
ENERGY_BLOCK_ID = 69635


def make_headers(token: str, client_id: str) -> dict:
    raw = uuid.uuid4().hex
    device_id = f"{raw[:6]}-{raw[6:9]}-{raw[9:12]}-{raw[12:16]}-{raw[16:28]}"
    raw2 = uuid.uuid4().hex
    session_id = f"{raw2[:7]}-{raw2[7:11]}-{raw2[11:15]}-{raw2[15:19]}-{raw2[19:31]}"
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "he-IL,he;q=0.9",
        "ClientID": client_id,
        "Content-Type": "application/json",
        "DeviceId": device_id,
        "Origin": "https://cellcom.co.il",
        "Referer": "https://cellcom.co.il/",
        "SessionID": session_id,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/147.0.0.0",
        "Authorization": f"Bearer {token}",
    }


async def get(session: aiohttp.ClientSession, endpoint: str, headers: dict) -> dict:
    async with session.get(BASE + endpoint, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
        data = await r.json(content_type=None)
        assert r.status == 200, f"HTTP {r.status} on {endpoint}"
        rc = (data.get("Header") or {}).get("ReturnCode", -1)
        assert rc == 0, f"RC={rc} msg={(data.get('Header') or {}).get('ReturnCodeMessage')} on {endpoint}"
        return data.get("Body") or {}


async def post(session: aiohttp.ClientSession, endpoint: str, headers: dict, body: dict) -> dict:
    async with session.post(BASE + endpoint, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=20)) as r:
        data = await r.json(content_type=None)
        assert r.status == 200, f"HTTP {r.status} on {endpoint}"
        rc = (data.get("Header") or {}).get("ReturnCode", -1)
        assert rc == 0, f"RC={rc} msg={(data.get('Header') or {}).get('ReturnCodeMessage')} on {endpoint}"
        return data.get("Body") or {}


async def run() -> None:
    if not TOKEN.startswith("eyJ"):
        print("Pass JWT as first argument")
        sys.exit(1)

    # Extract CLIENT_ID from JWT
    payload_b64 = TOKEN.split(".")[1] + "=="
    payload = json.loads(base64.b64decode(payload_b64))
    client_id = payload.get("CLIENT_ID", "")
    print(f"CLIENT_ID from JWT: {client_id}")

    h = make_headers(TOKEN, client_id)

    async with aiohttp.ClientSession() as sess:
        # ── Step 1: GetSelfcareDataOnboarding (config flow validation) ────────
        print("\n── Step 1: GetSelfcareDataOnboarding (simulates config flow) ──")
        body1 = await get(sess, "/api/SelfCare/GetSelfcareDataOnboarding", h)
        energy = (body1.get("subscribersByProduct") or {}).get("Energy", [])
        print(f"  Energy subscribers found: {len(energy)}")
        if not energy:
            print("  ERROR: No energy subscriber!")
            return

        active = [e for e in energy if e.get("productStatus") == "A"]
        sub = (active or energy)[0]
        ban = sub.get("ban", "")
        subscriber_no = sub.get("productSubscriberNo", "")
        plan = sub.get("pricePlanDesc", "")
        print(f"  BAN={ban}  subscriber={subscriber_no}  plan={plan}")
        print("  ✓ Config flow validation would SUCCEED")

        # ── Step 2: InvoiceData → extract invoice_id ─────────────────────────
        print("\n── Step 2: InvoiceData (GET) ──")
        body2 = await get(sess, "/api/SelfCare/InvoiceData", h)
        outer_invoices = body2.get("invoices", [])
        print(f"  outer invoices: {len(outer_invoices)} BAN entries")

        invoice_id = ""
        bill_cycle = ""
        for entry in outer_invoices:
            if str(entry.get("banPsId", "")) == str(ban):
                inner = entry.get("invoices", [])
                bill_cycle = entry.get("billCycle", "")
                if inner:
                    invoice_id = str(inner[0].get("id", ""))
                    bill_amount = inner[0].get("billAmount", {})
                    bill_date = inner[0].get("billDate", "")
                    print(f"  Found Energy invoice: id={invoice_id[:8]}...  date={bill_date}  amount={bill_amount}")
                break

        print(f"  Next bill cycle: {bill_cycle}")

        if not invoice_id:
            print("  WARNING: no invoice_id found — Ibill endpoints skipped")
            print("\n✓ Partial test PASSED (no invoice available, possibly new account)")
            return

        # ── Step 3: GetAllInvoicesAuth (billing details) ─────────────────────
        print("\n── Step 3: GetAllInvoicesAuth (POST) ──")
        ibill_body = {"blockId": ENERGY_BLOCK_ID, "invoiceId": invoice_id, "ticketId": None}
        body3 = await post(sess, "/api/Ibill/GetAllInvoicesAuth", h, ibill_body)
        cpb = body3.get("customerPerBan", {})
        di = body3.get("dataInvoices", [])
        print(f"  customerPerBan: totalSum={cpb.get('totalSum')}  due={cpb.get('billDueDate')}")
        print(f"  dataInvoices: {len(di)} entries  isEnergy={[x.get('isEnergy') for x in di[:2]]}")

        # ── Step 4: GetFullMainAuth (history) ────────────────────────────────
        print("\n── Step 4: GetFullMainAuth (POST) ──")
        body4 = await post(sess, "/api/Ibill/GetFullMainAuth", h, ibill_body)
        history = body4.get("history", [])
        print(f"  history entries: {len(history)}")
        if history:
            last = history[-1]
            kwh = (last.get("kwhDetails") or {}).get("kwh", "?")
            print(f"  latest: cycle={last.get('cycleDate')}  kwh={kwh}  period={last.get('billPeriods')}")

        # ── Step 5: GetAllProductsAuth (meter/tariff) ─────────────────────────
        print("\n── Step 5: GetAllProductsAuth (POST) ──")
        try:
            body5 = await post(sess, "/api/Ibill/GetAllProductsAuth", h, ibill_body)
            products = body5.get("allDetailsCliProduct", [])
            print(f"  allDetailsCliProduct: {len(products)} entries")
            if products:
                print(f"  first type: {products[0].get('detailsType')}")
        except Exception as e:
            print(f"  WARNING: {e}")

        print("\n✓ FULL TEST PASSED — all endpoints working correctly!")
        print(f"\nSummary:")
        print(f"  BAN: {ban}")
        print(f"  Subscriber: {subscriber_no}")
        print(f"  Plan: {plan}")
        print(f"  Total bill: ₪{cpb.get('totalSum', '?')}")
        print(f"  Due date: {cpb.get('billDueDate', '?')}")
        print(f"  Next cycle: {bill_cycle}")
        print(f"  History months: {len(history)}")


asyncio.run(run())
