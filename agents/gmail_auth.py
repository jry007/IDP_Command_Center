"""
Gmail OAuth helper — shared by all agents that read Gmail.
Run once per machine to authorize:
    python3 agents/gmail_auth.py
"""
import os, sys, pathlib
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

SCOPES      = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDS_PATH  = ROOT / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json")
TOKEN_PATH  = pathlib.Path(__file__).parent / "gmail_token.json"


def get_gmail_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDS_PATH}\n"
                    "Download OAuth 2.0 credentials from Google Cloud Console:\n"
                    "  console.cloud.google.com -> APIs & Services -> Credentials\n"
                    "  Create OAuth 2.0 Client ID (Desktop app) -> Download JSON\n"
                    f"  Save as: {CREDS_PATH}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())
        print(f"Gmail token saved to {TOKEN_PATH}")

    return build("gmail", "v1", credentials=creds)


def search_messages(service, query: str, max_results: int = 10) -> list:
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return result.get("messages", [])


def get_message(service, msg_id: str) -> dict:
    return service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()


def get_attachment(service, msg_id: str, attachment_id: str) -> bytes:
    import base64
    att = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()
    return base64.urlsafe_b64decode(att["data"])


def get_message_header(msg: dict, name: str) -> str:
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def iter_attachments(msg: dict):
    """Yields (filename, attachment_id) for all attachments in a message."""
    def walk(parts):
        for part in parts:
            if part.get("filename") and part["body"].get("attachmentId"):
                yield part["filename"], part["body"]["attachmentId"]
            if part.get("parts"):
                yield from walk(part["parts"])
    yield from walk(msg.get("payload", {}).get("parts", []))


if __name__ == "__main__":
    print("=== Gmail OAuth Setup ===\n")
    try:
        svc = get_gmail_service()
        profile = svc.users().getProfile(userId="me").execute()
        print(f"✓ Authorized as: {profile['emailAddress']}")
        print(f"  Token saved to: {TOKEN_PATH}")
        print("\nGmail setup complete!")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
