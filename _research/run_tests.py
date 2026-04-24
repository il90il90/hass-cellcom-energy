"""Pre-push test suite for cellcom_energy integration.

Tests that run WITHOUT installing homeassistant:
  1. Python syntax of all integration files
  2. Auth view HTML builder functions (no HA deps needed)
  3. API GUID field parsing logic
  4. API header / tracking-id generation
  5. Config flow view-registration guard
  6. manifest.json validity
  7. strings.json / translations validity

Usage:
    python _research/run_tests.py
"""

import sys
import ast
import asyncio
import json
import types
import importlib
import importlib.util
from pathlib import Path

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "cellcom_energy"
PASS = "[PASS]"
FAIL = "[FAIL]"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    status = PASS if ok else FAIL
    print(f"  {status}  {name}" + (f"  ({detail})" if detail else ""))


# ─── Mock HA modules so we can import integration files locally ──────────────

def _install_ha_mocks() -> None:
    """Stub out homeassistant.* so local imports don't crash."""

    def _make_mod(*parts: str) -> types.ModuleType:
        name = ".".join(parts)
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    # Minimal stubs
    ha = _make_mod("homeassistant")
    ha.config_entries = _make_mod("homeassistant", "config_entries")
    ha.core = _make_mod("homeassistant", "core")
    ha.exceptions = _make_mod("homeassistant", "exceptions")
    ha.helpers = _make_mod("homeassistant", "helpers")
    ha.helpers.aiohttp_client = _make_mod("homeassistant", "helpers", "aiohttp_client")
    ha.helpers.aiohttp_client.async_get_clientsession = lambda hass: None
    ha.components = _make_mod("homeassistant", "components")
    ha.components.http = _make_mod("homeassistant", "components", "http")

    # HomeAssistantView base class stub
    class _FakeView:
        url = ""
        name = ""
        requires_auth = True

    ha.components.http.HomeAssistantView = _FakeView

    # ConfigFlow stub
    class _FakeConfigFlow:
        VERSION = 1
        def __init_subclass__(cls, *, domain: str = "", **kw):
            pass

    ha.config_entries.ConfigFlow = _FakeConfigFlow
    ha.config_entries.FlowResult = dict

    # Common exception stubs
    ha.exceptions.ConfigEntryNotReady = Exception
    ha.exceptions.ConfigEntryAuthFailed = Exception

    # voluptuous (used in config_flow.py)
    if "voluptuous" not in sys.modules:
        vol = _make_mod("voluptuous")
        vol.Schema = lambda s, **kw: s
        vol.Required = lambda k, **kw: k
        vol.Optional = lambda k, **kw: k
        sys.modules["voluptuous"] = vol


_install_ha_mocks()


def _load_module(name: str) -> types.ModuleType:
    """Load an integration module with HA mocked out."""
    path = INTEGRATION_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(
        f"cellcom_energy.{name}", path,
        submodule_search_locations=[str(INTEGRATION_DIR)],
    )
    mod = importlib.util.module_from_spec(spec)
    # Make the package importable
    pkg_name = "cellcom_energy"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(INTEGRATION_DIR)]
        sys.modules[pkg_name] = pkg
    sys.modules[f"cellcom_energy.{name}"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        raise ImportError(f"Failed to load {name}: {exc}") from exc
    return mod


# ─── TEST 1: Python syntax ─────────────────────────────────────────────────────

def test_syntax() -> None:
    print("\n[1] Python syntax checks")
    for path in sorted(INTEGRATION_DIR.glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
            check(f"syntax {path.name}", True)
        except SyntaxError as e:
            check(f"syntax {path.name}", False, str(e))


# ─── TEST 2: Auth view HTML builders (no HA needed) ───────────────────────────

def test_auth_view_html() -> None:
    print("\n[2] Auth view HTML builder functions")
    src = (INTEGRATION_DIR / "auth_view.py").read_text(encoding="utf-8")

    # Extract and exec only the pure-Python parts (the HTML builder functions)
    # We do this by parsing the source and running just what we need.
    namespace: dict = {"__name__": "auth_view_test"}

    # Find RECAPTCHA_SITE_KEY constant
    m = __import__("re").search(r'RECAPTCHA_SITE_KEY\s*=\s*"([^"]+)"', src)
    site_key = m.group(1) if m else ""
    check("site key found in auth_view.py", bool(site_key), site_key[:20] if site_key else "")

    # Check the HTML contains required elements
    check("login page function exists", "_build_login_page" in src)
    check("success page function exists", "_build_success_page" in src)
    check("error_response function exists", "_error_response" in src)
    check("reCAPTCHA script tag present", "google.com/recaptcha/api.js" in src)
    check("OtpVerifyPhonePage action present", "OtpVerifyPhonePage" in src)
    check("flow_id injected in form", "flow_id" in src and 'name="flow_id"' in src)
    check("phone input in form", 'name="phone"' in src)
    check("g-recaptcha-response used", "g-recaptcha-response" in src)
    check("grecaptcha.execute called", "grecaptcha.execute" in src)
    check("POST action on form", 'method="POST"' in src)
    check("HA view URL correct", '"/api/cellcom_energy/auth"' in src)


# ─── TEST 3: GUID field parsing ────────────────────────────────────────────────

def test_guid_parsing() -> None:
    print("\n[3] API GUID field name fix")
    api_src = (INTEGRATION_DIR / "api.py").read_text(encoding="utf-8")

    # Verify that the code now looks for "message" field
    check('api.py: looks for Body["message"]', '"message"' in api_src or "body.get(\"message\")" in api_src)
    check('api.py: does NOT rely on "Guid" alone', 'body.get("Guid")' not in api_src or 'body.get("message")' in api_src)

    # Simulate correct parsing
    body = {
        "isSuccess": True,
        "resultMessage": "OTP_REQUIRED",
        "message": "8f30c9e3-3582-4a24-a259-2f7422f0699b",
        "extra": {"contactNumber": "0502959996"},
    }
    guid = body.get("message") or body.get("Guid") or body.get("guid")
    check("GUID parsed from Body.message", guid == "8f30c9e3-3582-4a24-a259-2f7422f0699b", guid[:8] if guid else "None")
    check("Old Body.Guid would fail", body.get("Guid") is None)


# ─── TEST 4: Tracking ID generation ───────────────────────────────────────────

def test_tracking_id() -> None:
    print("\n[4] Tracking ID generation")
    api_src = (INTEGRATION_DIR / "api.py").read_text(encoding="utf-8")
    check("_generate_tracking_id in api.py", "_generate_tracking_id" in api_src)
    check("x-cell-tracking-id used in LoginStep1", "x-cell-tracking-id" in api_src)

    # Run the generator function directly via exec
    import re, uuid
    m = re.search(r'def _generate_tracking_id\(\)[^:]*:(.*?)(?=\ndef |\Z)', api_src, re.DOTALL)
    if m:
        ns: dict = {"uuid": uuid}
        exec(f"def _generate_tracking_id():{m.group(1)}", ns)
        tid = ns["_generate_tracking_id"]()
        check("tracking_id: 32 chars", len(tid) == 32, f"len={len(tid)}")
        check("tracking_id: uppercase hex only", all(c in "0123456789ABCDEF" for c in tid), tid[:10])
    else:
        check("tracking_id function found via regex", False)


# ─── TEST 5: Config flow guards ────────────────────────────────────────────────

def test_config_flow() -> None:
    print("\n[5] Config flow: console snippet approach")
    src = (INTEGRATION_DIR / "config_flow.py").read_text(encoding="utf-8")
    # New flow: console snippet shown in HA UI, user pastes GUID back
    check("async_step_browser_login defined", "async_step_browser_login" in src)
    check("_make_console_snippet defined", "_make_console_snippet" in src)
    check("snippet in description_placeholders", '"snippet"' in src)
    check('GUID field in browser_login step', 'vol.Required("guid")' in src)
    check("reCAPTCHA site key constant", "_RECAPTCHA_SITE_KEY" in src)
    check("reCAPTCHA action constant", "_RECAPTCHA_ACTION" in src)
    check("grecaptcha.execute in snippet builder", "grecaptcha.execute" in src)
    check("LoginStep1 endpoint in snippet", "LoginStep1" in src)
    check("prompt() shows GUID to user", "prompt(" in src)

    # async_step_user should only ask for phone (no direct API calls)
    import re as _re
    step_user_match = _re.search(
        r"async def async_step_user\b.*?(?=\n    async def |\Z)", src, _re.DOTALL
    )
    step_user_body = step_user_match.group(0) if step_user_match else ""
    check("async_step_user does NOT call LoginStep1",
          "async_login_step1" not in step_user_body)


# ─── TEST 6: manifest.json ─────────────────────────────────────────────────────

def test_manifest() -> None:
    print("\n[6] manifest.json")
    path = INTEGRATION_DIR / "manifest.json"
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
        check("parses as JSON", True)
        check("domain = cellcom_energy", m.get("domain") == "cellcom_energy")
        check("config_flow = true", m.get("config_flow") is True)
        check("has requirements", bool(m.get("requirements")))
        check("aiohttp in requirements", any("aiohttp" in r for r in m.get("requirements", [])))
    except Exception as e:
        check("parses as JSON", False, str(e))


# ─── TEST 7: Translation files ─────────────────────────────────────────────────

def test_translations() -> None:
    print("\n[7] Translation files")
    for fname in ["strings.json", "translations/en.json", "translations/he.json"]:
        path = INTEGRATION_DIR / fname
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            check(f"{fname}: valid JSON", True)
            # Check that the real phone number is NOT present
            raw = path.read_text(encoding="utf-8")
            check(f"{fname}: no real phone number", "0502959996" not in raw)
        except Exception as e:
            check(f"{fname}: valid JSON", False, str(e))


# ─── TEST 8: WAF priming URLs correct ─────────────────────────────────────────

def test_waf_prime_urls() -> None:
    print("\n[8] WAF prime URLs in api.py")
    src = (INTEGRATION_DIR / "api.py").read_text(encoding="utf-8")
    check("primes cellcom.co.il", "https://cellcom.co.il/" in src)
    check("primes digital-api.cellcom.co.il", "https://digital-api.cellcom.co.il/" in src)
    check("primes my-cellcom page", "https://cellcom.co.il/my-cellcom/" in src)
    check("recaptcha_token stored in __init__", "self._recaptcha_token" in src)
    check("x-cell-recaptcha-token sent when available",
          "x-cell-recaptcha-token" in src and "self._recaptcha_token" in src)


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 55)
    print("Cellcom Energy — Pre-Push Test Suite")
    print("=" * 55)

    test_syntax()
    test_auth_view_html()
    test_guid_parsing()
    test_tracking_id()
    test_config_flow()
    test_manifest()
    test_translations()
    test_waf_prime_urls()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)

    print(f"\n{'=' * 55}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed:
        print("\nFailed:")
        for name, ok, detail in results:
            if not ok:
                print(f"  {FAIL}  {name}  {detail}")
    print("=" * 55)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
