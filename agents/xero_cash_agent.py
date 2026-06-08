"""
Xero Cash Position Agent
Pulls bank account balances from all connected Xero orgs and writes
a daily snapshot to the Notion Cash Position Daily database.

Schedule: 8:00 AM daily via launchd
"""
import os, sys, json, pathlib
from datetime import date
from dotenv import load_dotenv
from notion_client import Client

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config import NOTION_DB, CASH_FIELDS, XERO_ORG_MAP
from agents.xero_auth import ensure_valid_token, get_tenants

TENANT_PATH = pathlib.Path(__file__).parent / "xero_tenants.json"
NOTION_TOKEN = os.getenv("NOTION_TOKEN")


def get_bank_balance(access_token: str, tenant_id: str, org_name: str) -> float:
    """Fetch total bank balance for a Xero tenant using Reports API."""
    import requests
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }
    try:
        resp = requests.get(
            "https://api.xero.com/api.xro/2.0/Reports/BankSummary",
            headers=headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        total = 0.0
        reports = data.get("Reports", [])
        for report in reports:
            for row in report.get("Rows", []):
                for r in row.get("Rows", []):
                    cells = r.get("Cells", [])
                    if len(cells) >= 3:
                        try:
                            # Balance is typically the 3rd cell
                            val = cells[2].get("Value", "0").replace(",", "")
                            total += float(val or 0)
                        except (ValueError, AttributeError):
                            pass
        print(f"  {org_name}: ${total:,.2f}")
        return round(total, 2)

    except requests.HTTPError as e:
        if e.response.status_code == 403:
            print(f"  {org_name}: no access (403) — skipping")
        else:
            print(f"  {org_name}: HTTP {e.response.status_code} — skipping")
        return 0.0
    except Exception as e:
        print(f"  {org_name}: ERROR {e} — skipping")
        return 0.0


def fetch_all_balances() -> dict:
    """Returns { notion_field_name: balance } for all orgs."""
    if not TENANT_PATH.exists():
        print("ERROR: xero_tenants.json not found. Run: python3 agents/xero_auth.py")
        return {}

    access_token = ensure_valid_token()
    tenants = json.loads(TENANT_PATH.read_text())

    balances = {}
    for org_name, tenant_id in tenants.items():
        notion_field = XERO_ORG_MAP.get(org_name)
        if not notion_field:
            print(f"  {org_name}: no Notion field mapping — skipping")
            continue
        balance = get_bank_balance(access_token, tenant_id, org_name)
        balances[notion_field] = balance

    return balances


def write_to_notion(balances: dict):
    notion = Client(auth=NOTION_TOKEN)
    today  = str(date.today())
    total  = round(sum(balances.values()), 2)

    existing = notion.databases.query(
        database_id=NOTION_DB["cash_position"],
        filter={"property": "Date", "title": {"equals": today}}
    )

    props = {
        "Date":       {"title":  [{"text": {"content": today}}]},
        "Total Cash": {"number": total},
        **{k: {"number": v} for k, v in balances.items()},
    }

    if existing["results"]:
        notion.pages.update(existing["results"][0]["id"], properties=props)
        print(f"Updated cash position for {today} — Total: ${total:,.2f}")
    else:
        notion.pages.create(
            parent={"database_id": NOTION_DB["cash_position"]},
            properties=props
        )
        print(f"Created cash position for {today} — Total: ${total:,.2f}")


if __name__ == "__main__":
    print(f"=== Xero Cash Agent — {date.today()} ===")
    balances = fetch_all_balances()
    if balances:
        write_to_notion(balances)
        print("Done.")
    else:
        print("No balances fetched. Check Xero credentials.")
        sys.exit(1)
