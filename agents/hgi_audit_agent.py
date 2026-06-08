"""
HGI Night Audit Agent
- Searches Gmail for night audit PDF (subject contains "night audit")
- Parses KPIs using Claude API (document support)
- Writes to Notion HGI Daily Metrics database

Schedule: 7:45 AM daily via launchd
"""
import os, sys, json, re, base64, pathlib
from datetime import date, timedelta
from dotenv import load_dotenv
from agents.notion_helper import db_query, page_create, page_update, find_existing

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config import NOTION_DB
from agents.gmail_auth import get_gmail_service, search_messages, get_message, get_attachment, get_message_header, iter_attachments

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def find_audit_pdf(service, target_date: str) -> tuple[bytes, str] | tuple[None, None]:
    """Returns (pdf_bytes, filename) or (None, None)."""
    # Try targeted search first
    queries = [
        f'subject:"night audit" has:attachment filename:pdf after:{target_date}',
        'subject:"night audit" has:attachment filename:pdf newer_than:2d',
        'from:@hilton has:attachment filename:pdf newer_than:2d',
        'subject:"daily report" has:attachment filename:pdf newer_than:1d',
    ]
    for q in queries:
        messages = search_messages(service, q, max_results=5)
        for msg_ref in messages:
            msg = get_message(service, msg_ref["id"])
            for filename, att_id in iter_attachments(msg):
                if filename.lower().endswith(".pdf"):
                    pdf_bytes = get_attachment(service, msg_ref["id"], att_id)
                    print(f"  Found: {filename} ({len(pdf_bytes):,} bytes)")
                    return pdf_bytes, filename
    return None, None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import PyPDF2, io
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def parse_with_claude(pdf_bytes: bytes, report_date: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    prompt = f"""You are parsing a hotel night audit report for {report_date}.
Extract these metrics and return ONLY a valid JSON object (no markdown, no explanation):
{{
  "date": "{report_date}",
  "occupancy_pct": <decimal 0.00-1.00, e.g. 0.85 for 85%>,
  "rooms_sold": <integer>,
  "adr": <average daily rate in dollars, float>,
  "rev_par": <revenue per available room in dollars, float>,
  "room_revenue": <total room revenue in dollars, float>,
  "fb_revenue": <food and beverage revenue in dollars, float>,
  "total_revenue": <total revenue in dollars, float>,
  "notes": "<any notable items, or empty string>"
}}
Use null for any metric you cannot find. Do not include any text outside the JSON object."""

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )

    text = response.content[0].text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON in Claude response: {text[:200]}")


def write_to_notion(metrics: dict):
    report_date = metrics.get("date", str(date.today() - timedelta(days=1)))

    existing_id = find_existing(NOTION_DB["hgi_daily_metrics"], "Date", report_date)

    def num(key):
        v = metrics.get(key)
        return {"number": v} if v is not None else {"number": None}

    props = {
        "Date":          {"title":     [{"text": {"content": report_date}}]},
        "Occupancy %":   num("occupancy_pct"),
        "Rooms Sold":    num("rooms_sold"),
        "ADR":           num("adr"),
        "RevPAR":        num("rev_par"),
        "Room Revenue":  num("room_revenue"),
        "F&B Revenue":   num("fb_revenue"),
        "Total Revenue": num("total_revenue"),
        "Notes":         {"rich_text": [{"text": {"content": metrics.get("notes") or ""}}]},
    }

    if existing_id:
        page_update(existing_id, props)
        print(f"Updated HGI record for {report_date}")
    else:
        page_create(NOTION_DB["hgi_daily_metrics"], props)

    occ = (metrics.get("occupancy_pct") or 0) * 100
    adr = metrics.get("adr") or 0
    rev = metrics.get("rev_par") or 0
    print(f"HGI {report_date} — Occ: {occ:.1f}%  ADR: ${adr:.2f}  RevPAR: ${rev:.2f}")


if __name__ == "__main__":
    yesterday = str(date.today() - timedelta(days=1))
    print(f"=== HGI Audit Agent — processing {yesterday} ===")

    try:
        gmail = get_gmail_service()
        pdf_bytes, filename = find_audit_pdf(gmail, yesterday)

        if not pdf_bytes:
            print(f"No night audit PDF found for {yesterday}. Nothing written.")
            sys.exit(0)

        print(f"Parsing with Claude...")
        metrics = parse_with_claude(pdf_bytes, yesterday)

        write_to_notion(metrics)
        print("Done.")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
