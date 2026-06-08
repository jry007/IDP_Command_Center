"""
Xero Cash Position Agent
Pulls bank balances from each Xero org and writes a daily record to Notion.
Schedule via launchd at 8:00 AM daily.
"""
import os, sys
from datetime import date
from dotenv import load_dotenv
from notion_client import Client

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import NOTION_DB, XERO_ORGS

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
XERO_CLIENT_ID     = os.getenv("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")


def get_xero_balances():
    """
    Returns dict: { notion_field_name: balance_float }
    Uses xero-python SDK with stored OAuth tokens.
    Token refresh logic goes here — store tokens in agents/xero_tokens.json.
    """
    try:
        from xero_python.api_client import ApiClient
        from xero_python.api_client.configuration import Configuration
        from xero_python.api_client.oauth2 import OAuth2Token
        from xero_python.accounting import AccountingApi
        import json, pathlib

        token_path = pathlib.Path(__file__).parent / "xero_tokens.json"
        if not token_path.exists():
            print("ERROR: xero_tokens.json not found. Run xero_auth.py first.")
            return {}

        tokens = json.loads(token_path.read_text())

        config = Configuration()
        api_client = ApiClient(configuration=config,
                               oauth2_token=OAuth2Token(
                                   client_id=XERO_CLIENT_ID,
                                   client_secret=XERO_CLIENT_SECRET))
        api_client.set_oauth2_token(tokens["access_token"])
        accounting = AccountingApi(api_client)

        balances = {}
        for org in XERO_ORGS:
            if not org["id"]:
                continue
            try:
                tenant_id = org["id"]
                accounts = accounting.get_accounts(
                    xero_tenant_id=tenant_id,
                    where='Type=="BANK" AND Status=="ACTIVE"'
                )
                total = sum(
                    (a.balance or 0)
                    for a in (accounts.accounts or [])
                )
                balances[org["short"]] = round(total, 2)
                print(f"  {org['name']}: ${total:,.2f}")
            except Exception as e:
                print(f"  WARN: could not fetch {org['name']}: {e}")
                balances[org["short"]] = 0.0

        return balances

    except ImportError:
        print("xero-python not installed. pip install xero-python")
        return {}


def write_to_notion(balances: dict):
    notion = Client(auth=NOTION_TOKEN)
    today  = str(date.today())
    total  = sum(balances.values())

    # Check if today's record already exists
    existing = notion.databases.query(
        database_id=NOTION_DB["cash_position"],
        filter={"property": "Date", "title": {"equals": today}}
    )

    props = {
        "Date":       {"title": [{"text": {"content": today}}]},
        "Total Cash": {"number": total},
        **{k: {"number": v} for k, v in balances.items()}
    }

    if existing["results"]:
        page_id = existing["results"][0]["id"]
        notion.pages.update(page_id, properties=props)
        print(f"Updated existing Notion record for {today}")
    else:
        notion.pages.create(
            parent={"database_id": NOTION_DB["cash_position"]},
            properties=props
        )
        print(f"Created Notion record for {today} — Total: ${total:,.2f}")


if __name__ == "__main__":
    print(f"Xero Cash Agent — {date.today()}")
    balances = get_xero_balances()
    if balances:
        write_to_notion(balances)
    else:
        print("No balances retrieved. Check Xero credentials.")
