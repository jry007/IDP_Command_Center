"""
Xero OAuth 2.0 Authorization Setup
Run once to authorize all Xero orgs and save tenant tokens.

Usage:
    python3 agents/xero_auth.py
"""
import os, sys, json, webbrowser, pathlib
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading, requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

CLIENT_ID     = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8089/callback"
SCOPES        = "openid profile email accounting.reports.read accounting.settings.read offline_access"
TOKEN_PATH    = pathlib.Path(__file__).parent / "xero_tokens.json"
TENANT_PATH   = pathlib.Path(__file__).parent / "xero_tenants.json"

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html><body style='font-family:sans-serif;background:#0f0f1a;color:#a78bfa;text-align:center;padding:60px'>
            <h2>&#10003; Xero Authorization Successful</h2>
            <p style='color:#94a3b8'>You can close this tab and return to the terminal.</p>
            </body></html>""")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass


def get_tokens(code: str) -> dict:
    resp = requests.post("https://identity.xero.com/connect/token", data={
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    resp.raise_for_status()
    return resp.json()


def refresh_tokens(refresh_token: str) -> dict:
    resp = requests.post("https://identity.xero.com/connect/token", data={
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    resp.raise_for_status()
    return resp.json()


def get_tenants(access_token: str) -> list:
    resp = requests.get("https://api.xero.com/connections",
                        headers={"Authorization": f"Bearer {access_token}",
                                 "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


def load_tokens() -> dict | None:
    if TOKEN_PATH.exists():
        return json.loads(TOKEN_PATH.read_text())
    return None


def ensure_valid_token() -> str:
    """Load tokens, refresh if needed, return valid access_token."""
    tokens = load_tokens()
    if not tokens:
        raise RuntimeError("No tokens found. Run xero_auth.py first.")
    import time
    if tokens.get("expires_at", 0) < time.time() + 60:
        print("Refreshing Xero token...")
        new_tokens = refresh_tokens(tokens["refresh_token"])
        new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 1800)
        TOKEN_PATH.write_text(json.dumps(new_tokens, indent=2))
        return new_tokens["access_token"]
    return tokens["access_token"]


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: XERO_CLIENT_ID and XERO_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    print("\n=== Xero OAuth Setup ===\n")

    # Check for existing tokens
    existing = load_tokens()
    if existing:
        print("Existing tokens found. Refreshing...")
        try:
            new_tokens = refresh_tokens(existing["refresh_token"])
            import time
            new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 1800)
            TOKEN_PATH.write_text(json.dumps(new_tokens, indent=2))
            access_token = new_tokens["access_token"]
            print("Token refreshed successfully.")
        except Exception as e:
            print(f"Refresh failed ({e}). Re-authorizing...")
            existing = None

    if not existing:
        # Start local callback server
        server = HTTPServer(("localhost", 8089), CallbackHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        # Build auth URL
        auth_url = "https://login.xero.com/identity/connect/authorize?" + urlencode({
            "response_type": "code",
            "client_id":     CLIENT_ID,
            "redirect_uri":  REDIRECT_URI,
            "scope":         SCOPES,
            "state":         "idp_command_center",
        })

        print(f"Opening Xero authorization in browser...")
        print(f"If browser doesn't open, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)

        print("Waiting for authorization callback...", end="", flush=True)
        import time
        timeout = 120
        while auth_code is None and timeout > 0:
            time.sleep(1)
            timeout -= 1
            print(".", end="", flush=True)

        server.shutdown()
        print()

        if not auth_code:
            print("ERROR: Timed out waiting for authorization.")
            sys.exit(1)

        print("Authorization received. Fetching tokens...")
        tokens = get_tokens(auth_code)
        tokens["expires_at"] = time.time() + tokens.get("expires_in", 1800)
        TOKEN_PATH.write_text(json.dumps(tokens, indent=2))
        access_token = tokens["access_token"]
        print("Tokens saved.")

    # Fetch connected tenants
    print("\nFetching connected Xero organizations...")
    tenants = get_tenants(access_token)

    if not tenants:
        print("No tenants found. Make sure your Xero account has connected organizations.")
        sys.exit(1)

    print(f"\nFound {len(tenants)} organization(s):\n")
    tenant_map = {}
    for t in tenants:
        name = t["tenantName"]
        tid  = t["tenantId"]
        print(f"  ✓ {name} ({tid[:8]}...)")
        tenant_map[name] = tid

    TENANT_PATH.write_text(json.dumps(tenant_map, indent=2))
    print(f"\nTenant IDs saved to {TENANT_PATH}")
    print("\n✓ Xero setup complete! The cash agent will use these credentials automatically.")
