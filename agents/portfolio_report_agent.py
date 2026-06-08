"""
Weekly Portfolio Report Agent
- Monitors Gmail for Kim's Friday portfolio reports
- Parses the report using Claude to extract key updates and action items
- Logs the report in Notion Portfolio Reports database
- Creates Action Items in Notion for any items requiring follow-up

Schedule: Friday 6:00 PM + Monday 8:00 AM (to catch weekend emails) via launchd
"""
import os, sys, json, re, base64, io, pathlib
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
KIM_EMAIL         = os.getenv("KIM_EMAIL", "")  # Set in .env if known

REPORT_QUERIES = [
    f'from:{KIM_EMAIL} newer_than:7d' if KIM_EMAIL else None,
    'subject:"weekly report" newer_than:7d',
    'subject:"weekly update" newer_than:7d',
    'subject:"portfolio update" newer_than:7d',
    'subject:"friday report" newer_than:7d',
    'subject:"weekly summary" newer_than:7d',
    'subject:"weekly" has:attachment newer_than:7d',
]


def get_email_body(msg: dict) -> str:
    """Extract plain text body from Gmail message."""
    import base64 as b64

    def decode_part(part):
        data = part.get("body", {}).get("data", "")
        if data:
            return b64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        return ""

    payload = msg.get("payload", {})
    mime    = payload.get("mimeType", "")

    if mime == "text/plain":
        return decode_part(payload)

    if mime in ("multipart/alternative", "multipart/mixed", "multipart/related"):
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                text = decode_part(part)
                if text.strip():
                    return text
        # Fallback: grab first text part
        for part in payload.get("parts", []):
            text = decode_part(part)
            if text.strip():
                return text

    return msg.get("snippet", "")


def find_weekly_reports(service) -> list[dict]:
    seen_ids = set()
    reports  = []

    for query in REPORT_QUERIES:
        if not query:
            continue
        messages = search_messages(service, query, max_results=5)
        for msg_ref in messages:
            if msg_ref["id"] in seen_ids:
                continue
            seen_ids.add(msg_ref["id"])

            msg     = get_message(service, msg_ref["id"])
            subject = get_message_header(msg, "subject")
            sender  = get_message_header(msg, "from")
            msg_date = get_message_header(msg, "date")
            body    = get_email_body(msg)

            attachments = []
            for filename, att_id in iter_attachments(msg):
                ext = pathlib.Path(filename).suffix.lower()
                if ext in (".pdf", ".xlsx", ".xls", ".docx", ".csv"):
                    file_bytes = get_attachment(service, msg_ref["id"], att_id)
                    attachments.append({"filename": filename, "bytes": file_bytes, "ext": ext})

            reports.append({
                "id":          msg_ref["id"],
                "subject":     subject,
                "sender":      sender,
                "date":        msg_date,
                "body":        body,
                "attachments": attachments,
            })
            print(f"  Found: '{subject}' from {sender}")

    return reports


def extract_attachment_text(attachment: dict) -> str:
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
            for sheet in wb.worksheets:
                lines.append(f"\n--- Sheet: {sheet.title} ---")
                for row in sheet.iter_rows(values_only=True):
                    if any(c is not None for c in row):
                        lines.append("\t".join(str(c) if c is not None else "" for c in row))
            return "\n".join(lines)
        except Exception:
            return ""

    if ext == ".docx":
        try:
            import zipfile, xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return " ".join(t.text or "" for t in root.findall('.//w:t', ns))
        except Exception:
            return ""

    if ext == ".csv":
        return data.decode("utf-8", errors="replace")

    return ""


def analyze_with_claude(report: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build content: email body + attachment text
    content_parts = [f"Email Subject: {report['subject']}\nFrom: {report['sender']}\n\nEmail Body:\n{report['body'][:3000]}"]
    for att in report["attachments"]:
        text = extract_attachment_text(att)
        if text:
            content_parts.append(f"\n\nAttachment: {att['filename']}\n{text[:4000]}")

    full_content = "\n".join(content_parts)

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""You are analyzing a weekly portfolio report from Kim.
Extract the following and return ONLY valid JSON (no markdown, no explanation):
{{
  "week_ending": "<date YYYY-MM-DD or best estimate>",
  "summary": "<3-5 sentence summary of key updates this week>",
  "properties_mentioned": ["<property name>"],
  "action_items": [
    {{
      "item": "<specific action needed, attributed to the right person/property>",
      "priority": "High|Medium|Low",
      "category": "Finance|Operations|Legal|Deals|Hotel",
      "due_date": "<YYYY-MM-DD or null>"
    }}
  ],
  "flags": ["<anything that needs immediate attention>"],
  "reply_needed": <true|false>
}}

Report content:
{full_content}"""
        }]
    )

    text = response.content[0].text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"summary": full_content[:500], "action_items": [], "reply_needed": False}


def log_to_notion(report: dict, analysis: dict):
    week_end = analysis.get("week_ending", str(date.today()))
    title    = f"Kim's Report — Week Ending {week_end}"

    props = {
        "Report Title":  {"title":     [{"text": {"content": title}}]},
        "From":          {"rich_text": [{"text": {"content": report["sender"]}}]},
        "Email Subject": {"rich_text": [{"text": {"content": report["subject"]}}]},
        "Report Body":   {"rich_text": [{"text": {"content": analysis.get("summary","")[:2000]}}]},
        "Status":        {"select":    {"name": "Received"}},
        "Reply Sent":    {"checkbox":  False},
        "Received Date": {"date":      {"start": str(date.today())}},
    }
    if week_end:
        props["Week Ending"] = {"date": {"start": week_end}}

    page_create(NOTION_DB["portfolio_reports"], props)
    print(f"  Logged to Portfolio Reports: {title}")


def create_action_items(action_items: list, week_ending: str):
    for ai in action_items:
        item_text = ai.get("item", "")
        if not item_text:
            continue
        props = {
            "Action Item": {"title":     [{"text": {"content": item_text}}]},
            "Category":    {"select":    {"name": ai.get("category", "Operations")}},
            "Priority":    {"select":    {"name": ai.get("priority", "Medium")}},
            "Status":      {"select":    {"name": "Open"}},
            "Notes":       {"rich_text": [{"text": {"content": f"From Kim's report week ending {week_ending}"}}]},
        }
        due = ai.get("due_date")
        if due:
            props["Due Date"] = {"date": {"start": due}}

        page_create(NOTION_DB["action_items"], props)
        print(f"  Action item: {item_text[:70]}")


if __name__ == "__main__":
    print(f"=== Portfolio Report Agent — {date.today()} ===")

    try:
        gmail   = get_gmail_service()
        reports = find_weekly_reports(gmail)

        if not reports:
            print("No weekly portfolio reports found.")
            sys.exit(0)

        for report in reports:
            # Skip if already logged
            existing_id = find_existing(NOTION_DB["portfolio_reports"], "Email Subject", report["subject"])
            if existing_id:
                print(f"  Already logged: {report['subject']} — skipping")
                continue

            print(f"\nAnalyzing: {report['subject']}")
            analysis = analyze_with_claude(report)

            log_to_notion(report, analysis)

            action_items = analysis.get("action_items", [])
            if action_items:
                print(f"  Creating {len(action_items)} action item(s)...")
                create_action_items(action_items, analysis.get("week_ending", str(date.today())))

            flags = analysis.get("flags", [])
            if flags:
                print(f"  ⚠️  Flags: {'; '.join(flags)}")

        print(f"\nDone — processed {len(reports)} report(s).")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
