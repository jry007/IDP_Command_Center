"""
Gardant Assisted Living Reports Agent
- Monitors Gmail for Gardant financial/occupancy reports (Excel or PDF)
- Parses key metrics using Claude
- Creates Action Items in Notion for items requiring follow-up
- Logs the report in the Portfolio Reports database

Schedule: Daily at 9:00 AM via launchd
"""
import os, sys, json, re, base64, io, pathlib
from datetime import date, timedelta
from dotenv import load_dotenv
from notion_client import Client

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config import NOTION_DB
from agents.gmail_auth import (
    get_gmail_service, search_messages, get_message,
    get_attachment, get_message_header, iter_attachments
)

NOTION_TOKEN      = os.getenv("NOTION_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Gmail search queries to find Gardant reports
GARDANT_QUERIES = [
    'from:gardant has:attachment newer_than:7d',
    'subject:gardant has:attachment newer_than:7d',
    'subject:"assisted living" has:attachment newer_than:7d',
    'subject:"AL report" has:attachment newer_than:7d',
    'subject:"census report" has:attachment newer_than:7d',
    'subject:"monthly report" from:gardant newer_than:35d',
]


def find_gardant_reports(service) -> list[dict]:
    """Returns list of {filename, bytes, subject, sender, date}."""
    seen_ids = set()
    reports = []

    for query in GARDANT_QUERIES:
        messages = search_messages(service, query, max_results=10)
        for msg_ref in messages:
            if msg_ref["id"] in seen_ids:
                continue
            seen_ids.add(msg_ref["id"])

            msg = get_message(service, msg_ref["id"])
            subject = get_message_header(msg, "subject")
            sender  = get_message_header(msg, "from")
            msg_date = get_message_header(msg, "date")

            for filename, att_id in iter_attachments(msg):
                ext = pathlib.Path(filename).suffix.lower()
                if ext in (".pdf", ".xlsx", ".xls", ".csv"):
                    file_bytes = get_attachment(service, msg_ref["id"], att_id)
                    reports.append({
                        "filename": filename,
                        "bytes":    file_bytes,
                        "subject":  subject,
                        "sender":   sender,
                        "date":     msg_date,
                        "ext":      ext,
                    })
                    print(f"  Found: {filename} from {sender}")

    return reports


def extract_content(report: dict) -> str:
    """Extract text content from PDF or Excel."""
    ext   = report["ext"]
    data  = report["bytes"]

    if ext == ".pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(data))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            return f"[PDF parse error: {e}]"

    elif ext in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            lines = []
            for sheet in wb.worksheets:
                lines.append(f"Sheet: {sheet.title}")
                for row in sheet.iter_rows(values_only=True):
                    if any(c is not None for c in row):
                        lines.append("\t".join(str(c) if c is not None else "" for c in row))
            return "\n".join(lines)
        except Exception as e:
            return f"[Excel parse error: {e}]"

    elif ext == ".csv":
        return data.decode("utf-8", errors="replace")

    return ""


def analyze_with_claude(content: str, filename: str, subject: str) -> dict:
    """Ask Claude to extract key metrics and flag action items."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""You are analyzing a Gardant Assisted Living report.
File: {filename}
Email Subject: {subject}

Report Content:
{content[:8000]}

Extract the following and return ONLY valid JSON (no markdown):
{{
  "report_type": "<Census/Financial/Operational/Monthly Summary/Other>",
  "period": "<reporting period, e.g. May 2026>",
  "facility_name": "<facility name if shown>",
  "key_metrics": {{
    "occupancy_pct": <float or null>,
    "total_units": <int or null>,
    "occupied_units": <int or null>,
    "revenue": <float or null>,
    "expenses": <float or null>,
    "net_income": <float or null>
  }},
  "action_items": [
    {{"item": "<specific action needed>", "priority": "High|Medium|Low", "category": "Operations|Finance|Legal"}}
  ],
  "summary": "<2-3 sentence summary of the report>"
}}"""
        }]
    )

    text = response.content[0].text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"summary": content[:500], "action_items": []}


def log_to_notion_portfolio(report: dict, analysis: dict):
    """Log the report in the Portfolio Reports / Weekly Portfolio Log DB."""
    notion = Client(auth=NOTION_TOKEN)
    title  = f"Gardant: {analysis.get('report_type','Report')} — {analysis.get('period', str(date.today()))}"

    notion.pages.create(
        parent={"database_id": NOTION_DB["portfolio_reports"]},
        properties={
            "Report Title":  {"title":     [{"text": {"content": title}}]},
            "From":          {"rich_text": [{"text": {"content": report["sender"]}}]},
            "Email Subject": {"rich_text": [{"text": {"content": report["subject"]}}]},
            "Report Body":   {"rich_text": [{"text": {"content": analysis.get("summary","")[:2000]}}]},
            "Status":        {"select":    {"name": "Received"}},
            "Received Date": {"date":      {"start": str(date.today())}},
        }
    )
    print(f"  Logged to Portfolio Reports: {title}")


def create_action_items(action_items: list, source: str):
    notion = Client(auth=NOTION_TOKEN)
    for ai in action_items:
        item_text = ai.get("item", "")
        if not item_text:
            continue
        notion.pages.create(
            parent={"database_id": NOTION_DB["action_items"]},
            properties={
                "Action Item": {"title":     [{"text": {"content": f"[Gardant] {item_text}"}}]},
                "Category":    {"select":    {"name": ai.get("category", "Operations")}},
                "Priority":    {"select":    {"name": ai.get("priority", "Medium")}},
                "Status":      {"select":    {"name": "Open"}},
                "Notes":       {"rich_text": [{"text": {"content": f"Source: {source}"}}]},
            }
        )
        print(f"  Action item created: {item_text[:60]}")


if __name__ == "__main__":
    print(f"=== Gardant AL Agent — {date.today()} ===")

    try:
        gmail   = get_gmail_service()
        reports = find_gardant_reports(gmail)

        if not reports:
            print("No Gardant reports found in Gmail.")
            sys.exit(0)

        for report in reports:
            print(f"\nAnalyzing: {report['filename']}")
            content  = extract_content(report)
            analysis = analyze_with_claude(content, report["filename"], report["subject"])

            log_to_notion_portfolio(report, analysis)

            action_items = analysis.get("action_items", [])
            if action_items:
                print(f"  Creating {len(action_items)} action item(s)...")
                create_action_items(action_items, report["filename"])
            else:
                print("  No action items flagged.")

        print(f"\nDone — processed {len(reports)} report(s).")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
