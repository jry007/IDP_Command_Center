"""
Leasing Follow-Up Agent
- Monitors Gmail for AppFolio weekly owner statements and leasing activity
- Parses occupancy, rent roll, and delinquency data
- Creates follow-up action items in Notion for anything requiring attention
- Runs weekly on Monday mornings

Schedule: Monday 8:30 AM via launchd
"""
import os, sys, json, re, io, pathlib
from datetime import date, timedelta
from dotenv import load_dotenv
from agents.notion_helper import db_query, page_create, page_update, find_existing

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from config import NOTION_DB
from agents.gmail_auth import (
    get_gmail_service, search_messages, get_message,
    get_attachment, get_message_header, iter_attachments
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

LEASING_QUERIES = [
    'from:appfolio has:attachment newer_than:7d',
    'subject:"owner statement" has:attachment newer_than:35d',
    'subject:"rent roll" has:attachment newer_than:35d',
    'subject:"leasing report" newer_than:14d',
    'subject:"delinquency" newer_than:14d',
    'subject:"vacancy" newer_than:14d',
    'subject:"appfolio" newer_than:7d',
]


def find_leasing_reports(service) -> list[dict]:
    seen_ids = set()
    reports  = []

    for query in LEASING_QUERIES:
        messages = search_messages(service, query, max_results=10)
        for msg_ref in messages:
            if msg_ref["id"] in seen_ids:
                continue
            seen_ids.add(msg_ref["id"])

            msg     = get_message(service, msg_ref["id"])
            subject = get_message_header(msg, "subject")
            sender  = get_message_header(msg, "from")

            attachments = []
            for filename, att_id in iter_attachments(msg):
                ext = pathlib.Path(filename).suffix.lower()
                if ext in (".pdf", ".xlsx", ".xls", ".csv"):
                    file_bytes = get_attachment(service, msg_ref["id"], att_id)
                    attachments.append({"filename": filename, "bytes": file_bytes, "ext": ext})

            if attachments:
                reports.append({
                    "id":          msg_ref["id"],
                    "subject":     subject,
                    "sender":      sender,
                    "attachments": attachments,
                })
                print(f"  Found: '{subject}' ({len(attachments)} attachment(s))")

    return reports


def extract_content(attachment: dict) -> str:
    ext  = attachment["ext"]
    data = attachment["bytes"]

    if ext == ".pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(data))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return ""

    if ext in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            lines = []
            for sheet in wb.worksheets[:3]:  # limit to first 3 sheets
                lines.append(f"Sheet: {sheet.title}")
                for i, row in enumerate(sheet.iter_rows(values_only=True)):
                    if i > 200:
                        break
                    if any(c is not None for c in row):
                        lines.append("\t".join(str(c) if c is not None else "" for c in row))
            return "\n".join(lines)
        except Exception:
            return ""

    if ext == ".csv":
        return data.decode("utf-8", errors="replace")[:8000]

    return ""


def analyze_with_claude(subject: str, content: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Analyze this property management / leasing report.
Email: {subject}

Content:
{content[:7000]}

Return ONLY valid JSON (no markdown):
{{
  "report_type": "<Owner Statement|Rent Roll|Delinquency|Vacancy|Leasing Activity|Other>",
  "period": "<reporting period>",
  "properties": ["<property names found>"],
  "key_metrics": {{
    "total_units": <int or null>,
    "occupied_units": <int or null>,
    "occupancy_pct": <float 0-1 or null>,
    "total_rent_collected": <float or null>,
    "delinquent_amount": <float or null>,
    "delinquent_units": <int or null>,
    "vacant_units": <int or null>
  }},
  "action_items": [
    {{
      "item": "<specific follow-up needed>",
      "priority": "High|Medium|Low",
      "category": "Finance|Operations|Legal"
    }}
  ],
  "summary": "<2-3 sentences about this report>"
}}"""
        }]
    )

    text = response.content[0].text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"summary": content[:300], "action_items": []}


def create_action_items(action_items: list, source: str):
    for ai in action_items:
        item_text = ai.get("item", "")
        if not item_text:
            continue
        page_create(NOTION_DB["action_items"], {
            "Action Item": {"title":     [{"text": {"content": f"[Leasing] {item_text}"}}]},
            "Category":    {"select":    {"name": ai.get("category", "Operations")}},
            "Priority":    {"select":    {"name": ai.get("priority", "Medium")}},
            "Status":      {"select":    {"name": "Open"}},
            "Notes":       {"rich_text": [{"text": {"content": f"Source: {source}"}}]},
        })
        print(f"  Action item: {item_text[:70]}")


if __name__ == "__main__":
    print(f"=== Leasing Follow-Up Agent — {date.today()} ===")

    try:
        gmail   = get_gmail_service()
        reports = find_leasing_reports(gmail)

        if not reports:
            print("No leasing reports found in Gmail.")
            sys.exit(0)

        total_actions = 0
        for report in reports:
            for att in report["attachments"]:
                print(f"\nAnalyzing: {att['filename']}")
                content  = extract_content(att)
                if not content.strip():
                    print("  Could not extract text — skipping")
                    continue

                analysis = analyze_with_claude(report["subject"], content)
                print(f"  Type: {analysis.get('report_type')} | Summary: {analysis.get('summary','')[:80]}")

                action_items = analysis.get("action_items", [])
                if action_items:
                    create_action_items(action_items, att["filename"])
                    total_actions += len(action_items)
                else:
                    print("  No action items flagged.")

        print(f"\nDone — {total_actions} action item(s) created.")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
