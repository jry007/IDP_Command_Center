"""
HGI Night Audit Agent
- Checks Gmail for night audit PDF attachments
- Parses metrics using Claude API
- Writes daily record to Notion HGI Daily Metrics DB
Schedule via launchd at 7:45 AM daily.
"""
import os, sys, base64, json, re
from datetime import date, timedelta
from dotenv import load_dotenv
from notion_client import Client

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import NOTION_DB

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

NOTION_TOKEN       = os.getenv("NOTION_TOKEN")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GMAIL_CREDS_PATH   = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json")


def get_gmail_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import pathlib

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
    token_path = pathlib.Path(__file__).parent / "gmail_token.json"
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_audit_pdf(gmail, target_date: str) -> bytes | None:
    """Search Gmail for night audit PDF for target_date (YYYY-MM-DD)."""
    query = f'subject:"night audit" has:attachment filename:pdf after:{target_date} before:{target_date}'
    results = gmail.users().messages().list(userId="me", q=query, maxResults=5).execute()
    messages = results.get("messages", [])

    if not messages:
        # Try broader search
        query = 'subject:"night audit" has:attachment filename:pdf'
        results = gmail.users().messages().list(userId="me", q=query, maxResults=3).execute()
        messages = results.get("messages", [])

    for msg_ref in messages:
        msg = gmail.users().messages().get(userId="me", id=msg_ref["id"]).execute()
        for part in msg.get("payload", {}).get("parts", []):
            if part.get("filename", "").lower().endswith(".pdf"):
                att_id = part["body"].get("attachmentId")
                if att_id:
                    att = gmail.users().messages().attachments().get(
                        userId="me", messageId=msg_ref["id"], id=att_id).execute()
                    return base64.urlsafe_b64decode(att["data"])
    return None


def parse_with_claude(pdf_bytes: bytes) -> dict:
    """Use Claude to extract metrics from the night audit PDF."""
    import anthropic, base64

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}
                },
                {
                    "type": "text",
                    "text": """Extract the following metrics from this hotel night audit report.
Return ONLY a valid JSON object with these exact keys (use null if not found):
{
  "date": "YYYY-MM-DD",
  "occupancy_pct": 0.00,
  "rooms_sold": 0,
  "adr": 0.00,
  "rev_par": 0.00,
  "room_revenue": 0.00,
  "fb_revenue": 0.00,
  "total_revenue": 0.00,
  "notes": ""
}
occupancy_pct should be a decimal (e.g. 0.85 for 85%). Do not include any text outside the JSON."""
                }
            ]
        }]
    )

    text = response.content[0].text.strip()
    # Extract JSON if wrapped in markdown code block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {}


def write_to_notion(metrics: dict):
    notion = Client(auth=NOTION_TOKEN)
    report_date = metrics.get("date", str(date.today() - timedelta(days=1)))

    existing = notion.databases.query(
        database_id=NOTION_DB["hgi_daily_metrics"],
        filter={"property": "Date", "title": {"equals": report_date}}
    )

    props = {
        "Date":          {"title": [{"text": {"content": report_date}}]},
        "Occupancy %":   {"number": metrics.get("occupancy_pct")},
        "Rooms Sold":    {"number": metrics.get("rooms_sold")},
        "ADR":           {"number": metrics.get("adr")},
        "RevPAR":        {"number": metrics.get("rev_par")},
        "Room Revenue":  {"number": metrics.get("room_revenue")},
        "F&B Revenue":   {"number": metrics.get("fb_revenue")},
        "Total Revenue": {"number": metrics.get("total_revenue")},
        "Notes":         {"rich_text": [{"text": {"content": metrics.get("notes") or ""}}]},
    }
    # Remove null values
    props = {k: v for k, v in props.items()
             if not (isinstance(v, dict) and v.get("number") is None)}

    if existing["results"]:
        notion.pages.update(existing["results"][0]["id"], properties=props)
        print(f"Updated HGI record for {report_date}")
    else:
        notion.pages.create(
            parent={"database_id": NOTION_DB["hgi_daily_metrics"]},
            properties=props
        )
        print(f"Created HGI record for {report_date} — Occ: {metrics.get('occupancy_pct',0)*100:.1f}%")


if __name__ == "__main__":
    yesterday = str(date.today() - timedelta(days=1))
    print(f"HGI Audit Agent — processing {yesterday}")

    try:
        gmail   = get_gmail_service()
        pdf     = fetch_audit_pdf(gmail, yesterday)
        if not pdf:
            print(f"No night audit PDF found for {yesterday}")
            sys.exit(0)
        print(f"Found PDF ({len(pdf):,} bytes). Parsing with Claude...")
        metrics = parse_with_claude(pdf)
        if not metrics:
            print("Could not parse metrics from PDF.")
            sys.exit(1)
        print(f"Parsed: Occ={metrics.get('occupancy_pct',0)*100:.1f}% "
              f"ADR=${metrics.get('adr',0):.2f} "
              f"RevPAR=${metrics.get('rev_par',0):.2f}")
        write_to_notion(metrics)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
